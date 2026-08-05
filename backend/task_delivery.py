"""Turn an operator-approved entity into a native Bitrix task."""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID

from psycopg import Connection

from backend.repository import (
    ConflictError,
    finish_task_attempt,
    get_candidate,
    get_operator_bitrix_user_id,
    prepare_confirmed_task,
    resolve_task_destination,
)
from backend.schemas import (
    ConfirmCandidatePayload,
    SessionUserDto,
    TaskCandidateDto,
)
from bitrix import BitrixAPIError, BitrixClient, BitrixError


DEFAULT_TASK_DEPARTMENT_ID = 82
DEFAULT_TASK_ADD_METHOD = "task.item.add"


@dataclass(frozen=True, slots=True)
class TaskDeliveryConfig:
    default_department_id: int
    add_method: str

    @classmethod
    def from_env(cls) -> "TaskDeliveryConfig":
        raw_department_id = os.getenv(
            "BITRIX_TASK_DEFAULT_DEPARTMENT_ID",
            os.getenv(
                "BITRIX_OPERATOR_DEPARTMENT_ID",
                str(DEFAULT_TASK_DEPARTMENT_ID),
            ),
        )
        try:
            department_id = int(raw_department_id)
        except ValueError as exc:
            raise RuntimeError(
                "BITRIX_TASK_DEFAULT_DEPARTMENT_ID must be an integer"
            ) from exc
        if department_id <= 0:
            raise RuntimeError(
                "BITRIX_TASK_DEFAULT_DEPARTMENT_ID must be positive"
            )
        add_method = os.getenv(
            "BITRIX_TASK_ADD_METHOD",
            DEFAULT_TASK_ADD_METHOD,
        ).strip()
        if add_method not in {"task.item.add", "tasks.task.add"}:
            raise RuntimeError(
                "BITRIX_TASK_ADD_METHOD must be task.item.add or tasks.task.add"
            )
        return cls(
            default_department_id=department_id,
            add_method=add_method,
        )


def deliver_candidate(
    connection: Connection,
    *,
    candidate_id: UUID,
    actor: SessionUserDto,
    payload: ConfirmCandidatePayload,
    retry: bool,
    client: BitrixClient | None = None,
    config: TaskDeliveryConfig | None = None,
) -> TaskCandidateDto:
    """Persist the edited task, route it, attempt delivery, and return state."""

    resolved_config = config or TaskDeliveryConfig.from_env()
    candidate = get_candidate(connection, candidate_id)
    _require_concrete_complaint(candidate)
    destination = resolve_task_destination(
        connection,
        department_id=payload.department_id,
        department_label=payload.department,
        default_department_id=resolved_config.default_department_id,
    )
    task_row = prepare_confirmed_task(
        connection,
        candidate_id=candidate_id,
        actor=actor,
        payload=payload,
        department_id=destination["department_id"],
        department_label=destination["department"],
        responsible_bitrix_user_id=destination[
            "responsible_bitrix_user_id"
        ],
        bitrix_method=resolved_config.add_method,
        retry=retry,
    )
    initiator_bitrix_id = get_operator_bitrix_user_id(connection, actor.id)
    responsible_bitrix_id = task_row["responsible_bitrix_user_id"]
    fields = {
        "TITLE": task_row["title"],
        "DESCRIPTION": _task_description(task_row),
        "RESPONSIBLE_ID": responsible_bitrix_id,
        "PRIORITY": _bitrix_priority(task_row["priority"]),
    }
    if initiator_bitrix_id != responsible_bitrix_id:
        fields["AUDITORS"] = [initiator_bitrix_id]
    request_payload = {
        "method": resolved_config.add_method,
        "fields": fields,
    }

    resolved_client = client or BitrixClient.from_env()
    try:
        result = resolved_client.task_add(
            fields=fields,
            method=resolved_config.add_method,
        )
    except BitrixError as exc:
        finish_task_attempt(
            connection,
            confirmed_task_id=task_row["id"],
            request_payload=request_payload,
            response_payload=None,
            bitrix_item_id=None,
            error_code=exc.code if isinstance(exc, BitrixAPIError) else None,
            error_message=str(exc),
        )
    else:
        finish_task_attempt(
            connection,
            confirmed_task_id=task_row["id"],
            request_payload=request_payload,
            response_payload=dict(result.raw_response),
            bitrix_item_id=result.task_id,
            error_code=None,
            error_message=None,
        )
    return get_candidate(connection, candidate_id)


def _task_description(task_row: dict) -> str:
    details = [
        f"Подразделение: {task_row['department']}",
        f"Источник: звонок {task_row['call_id']}",
    ]
    description = task_row["description"].strip()
    if description:
        return f"{description}\n\n" + "\n".join(details)
    return "\n".join(details)


def _bitrix_priority(priority: int) -> str:
    if priority <= 2:
        return "0"
    if priority == 3:
        return "1"
    return "2"


def _require_concrete_complaint(candidate: TaskCandidateDto) -> None:
    if (
        not candidate.should_create
        or candidate.complaint_basis != "explicit_complaint"
        or candidate.is_concrete_complaint is not True
        or not candidate.complaint_subject.strip()
        or not candidate.complaint_issue.strip()
    ):
        raise ConflictError(
            "Bitrix task requires a concrete customer complaint with a "
            "specific subject and issue"
        )


__all__ = [
    "TaskDeliveryConfig",
    "_require_concrete_complaint",
    "deliver_candidate",
]
