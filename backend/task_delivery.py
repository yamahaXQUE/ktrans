"""Turn an operator-approved entity into portal-specific ``crm.item.add``."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg import Connection

from backend.repository import (
    finish_task_attempt,
    get_candidate,
    get_operator_bitrix_user_id,
    prepare_confirmed_task,
)
from backend.schemas import (
    ConfirmCandidatePayload,
    SessionUserDto,
    TaskCandidateDto,
)
from backend.task_create import ConfirmedTask
from bitrix import BitrixAPIError, BitrixClient, BitrixError, BitrixTaskMapper


DEFAULT_TASK_ENTITY_TYPE_ID = 1034
DEFAULT_FIELD_MAPPING = {"title": "title"}
DEFAULT_CONSTANT_FIELDS = {"opened": True}


@dataclass(frozen=True, slots=True)
class TaskDeliveryConfig:
    entity_type_id: int
    mapper: BitrixTaskMapper

    @classmethod
    def from_env(cls) -> "TaskDeliveryConfig":
        raw_entity_type_id = os.getenv(
            "BITRIX_TASK_ENTITY_TYPE_ID",
            str(DEFAULT_TASK_ENTITY_TYPE_ID),
        )
        try:
            entity_type_id = int(raw_entity_type_id)
        except ValueError as exc:
            raise RuntimeError(
                "BITRIX_TASK_ENTITY_TYPE_ID must be an integer"
            ) from exc
        if entity_type_id <= 0:
            raise RuntimeError("BITRIX_TASK_ENTITY_TYPE_ID must be positive")

        mapping = _json_object_env(
            "BITRIX_TASK_FIELD_MAPPING",
            DEFAULT_FIELD_MAPPING,
        )
        constants = _json_object_env(
            "BITRIX_TASK_CONSTANT_FIELDS",
            DEFAULT_CONSTANT_FIELDS,
        )
        if not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in mapping.items()
        ):
            raise RuntimeError(
                "BITRIX_TASK_FIELD_MAPPING must map strings to strings"
            )
        return cls(
            entity_type_id=entity_type_id,
            mapper=BitrixTaskMapper(
                mapping,
                constant_fields=constants,
            ),
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
    """Persist the edited task, attempt Bitrix delivery, and return feed state."""

    resolved_config = config or TaskDeliveryConfig.from_env()
    task_row = prepare_confirmed_task(
        connection,
        candidate_id=candidate_id,
        actor=actor,
        payload=payload,
        entity_type_id=resolved_config.entity_type_id,
        retry=retry,
    )
    initiator_bitrix_id = get_operator_bitrix_user_id(connection, actor.id)
    task = ConfirmedTask(
        source_call_id=str(task_row["call_id"]),
        title=task_row["title"],
        description=task_row["description"],
        department=task_row["department"],
        initiator=initiator_bitrix_id,
        priority=task_row["priority"],
    )
    fields = resolved_config.mapper.to_bitrix_fields(task)
    request_payload = {
        "entityTypeId": resolved_config.entity_type_id,
        "fields": fields,
    }

    resolved_client = client or BitrixClient.from_env()
    try:
        result = resolved_client.crm_item_add(
            entity_type_id=resolved_config.entity_type_id,
            fields=fields,
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
            bitrix_item_id=result.item_id,
            error_code=None,
            error_message=None,
        )
    return get_candidate(connection, candidate_id)


def _json_object_env(
    name: str,
    default: dict[str, Any],
) -> dict[str, Any]:
    raw = os.getenv(name)
    if raw is None:
        return dict(default)
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name} must be valid JSON") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError(f"{name} must be a JSON object")
    return decoded


__all__ = [
    "TaskDeliveryConfig",
    "deliver_candidate",
]
