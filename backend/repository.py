"""PostgreSQL queries and state transitions for the frontend API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from backend.schemas import (
    ComplaintAnalyticsDto,
    ComplaintDepartmentStatDto,
    ConfirmCandidatePayload,
    DepartmentDto,
    OperatorSummaryDto,
    SessionUserDto,
    SourceCallDto,
    TaskCandidateDto,
)


class NotFoundError(LookupError):
    pass


class ConflictError(RuntimeError):
    pass


class PermissionDeniedError(RuntimeError):
    pass


def get_operator_by_bitrix_user_id(
    connection: Connection,
    bitrix_user_id: int,
) -> SessionUserDto:
    row = connection.execute(
        """
        SELECT
            operator.id,
            operator.display_name,
            operator.work_position,
            operator.role::text AS role,
            COALESCE(
                array_agg(membership.department_id ORDER BY membership.is_primary DESC)
                    FILTER (WHERE membership.department_id IS NOT NULL),
                '{}'::bigint[]
            ) AS department_ids
        FROM operators AS operator
        LEFT JOIN operator_departments AS membership
            ON membership.operator_id = operator.id
        WHERE operator.bitrix_user_id = %s
          AND operator.active
        GROUP BY operator.id
        """,
        (bitrix_user_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError(
            f"Bitrix user {bitrix_user_id} is not a synced active operator"
        )
    return _session_user(row, source="bitrix")


def get_operator_by_id(
    connection: Connection,
    operator_id: UUID,
    *,
    source: str = "local",
) -> SessionUserDto:
    row = connection.execute(
        """
        SELECT
            operator.id,
            operator.display_name,
            operator.work_position,
            operator.role::text AS role,
            COALESCE(
                array_agg(membership.department_id ORDER BY membership.is_primary DESC)
                    FILTER (WHERE membership.department_id IS NOT NULL),
                '{}'::bigint[]
            ) AS department_ids
        FROM operators AS operator
        LEFT JOIN operator_departments AS membership
            ON membership.operator_id = operator.id
        WHERE operator.id = %s
          AND operator.active
        GROUP BY operator.id
        """,
        (operator_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Operator {operator_id} not found")
    return _session_user(row, source=source)


def get_operator_bitrix_user_id(
    connection: Connection,
    operator_id: UUID,
) -> int:
    row = connection.execute(
        """
        SELECT bitrix_user_id
        FROM operators
        WHERE id = %s
          AND active
        """,
        (operator_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Operator {operator_id} not found")
    return int(row["bitrix_user_id"])


def create_session(
    connection: Connection,
    operator_id: UUID,
    *,
    member_id: str | None,
    lifetime: timedelta = timedelta(hours=8),
) -> UUID:
    session_id = uuid4()
    connection.execute(
        """
        INSERT INTO user_sessions (
            id,
            operator_id,
            bitrix_member_id,
            expires_at
        )
        VALUES (%s, %s, %s, %s)
        """,
        (
            session_id,
            operator_id,
            member_id,
            datetime.now(timezone.utc) + lifetime,
        ),
    )
    return session_id


def get_session_user(
    connection: Connection,
    session_id: UUID,
) -> SessionUserDto:
    row = connection.execute(
        """
        UPDATE user_sessions
        SET last_seen_at = now()
        WHERE id = %s
          AND expires_at > now()
        RETURNING operator_id
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError("Session not found or expired")
    return get_operator_by_id(
        connection,
        row["operator_id"],
        source="bitrix",
    )


def list_emulation_users(connection: Connection) -> list[SessionUserDto]:
    rows = connection.execute(
        """
        SELECT
            operator.id,
            operator.display_name,
            operator.work_position,
            operator.role::text AS role,
            COALESCE(
                array_agg(membership.department_id ORDER BY membership.is_primary DESC)
                    FILTER (WHERE membership.department_id IS NOT NULL),
                '{}'::bigint[]
            ) AS department_ids
        FROM operators AS operator
        LEFT JOIN operator_departments AS membership
            ON membership.operator_id = operator.id
        WHERE operator.active
        GROUP BY operator.id
        ORDER BY
            CASE WHEN operator.role = 'supervisor' THEN 0 ELSE 1 END,
            lower(operator.display_name),
            operator.id
        """
    ).fetchall()
    return [_session_user(row, source="local") for row in rows]


def list_departments(connection: Connection) -> list[DepartmentDto]:
    rows = connection.execute(
        """
        SELECT bitrix_department_id AS id, name
        FROM departments
        WHERE active
        ORDER BY lower(name), bitrix_department_id
        """
    ).fetchall()
    return [DepartmentDto.model_validate(row) for row in rows]


def list_operator_summaries(
    connection: Connection,
) -> list[OperatorSummaryDto]:
    rows = connection.execute(
        """
        SELECT *
        FROM operator_dashboard
        ORDER BY lower(display_name), id
        """
    ).fetchall()
    return [
        OperatorSummaryDto(
            **row,
            initials=_initials(row["display_name"]),
        )
        for row in rows
    ]


def get_complaint_analytics(
    connection: Connection,
) -> ComplaintAnalyticsDto:
    rows = connection.execute(
        """
        SELECT
            COALESCE(
                NULLIF(btrim(task.department_label), ''),
                department.name,
                'Без отдела'
            ) AS department,
            count(*)::integer AS complaint_count
        FROM confirmed_tasks AS task
        JOIN task_candidates AS candidate
            ON candidate.id = task.candidate_id
        LEFT JOIN departments AS department
            ON department.bitrix_department_id = task.department_id
        WHERE task.delivery_status = 'created'
          AND task.bitrix_item_id IS NOT NULL
          AND candidate.complaint_basis IN (
              'explicit_complaint',
              'explicit_negative_feedback'
          )
        GROUP BY 1
        ORDER BY complaint_count DESC, lower(
            COALESCE(
                NULLIF(btrim(task.department_label), ''),
                department.name,
                'Без отдела'
            )
        )
        """
    ).fetchall()
    total = sum(int(row["complaint_count"]) for row in rows)
    departments = [
        ComplaintDepartmentStatDto(
            department=row["department"],
            count=int(row["complaint_count"]),
            share_percent=(
                round(int(row["complaint_count"]) * 100 / total, 1)
                if total
                else 0
            ),
        )
        for row in rows
    ]
    return ComplaintAnalyticsDto(
        total_complaints=total,
        generated_at=datetime.now(timezone.utc),
        departments=departments,
    )


def list_complaint_export_rows(
    connection: Connection,
) -> list[dict[str, Any]]:
    return connection.execute(
        """
        SELECT
            task.updated_at AS sent_at,
            task.bitrix_item_id,
            operator.display_name AS operator_name,
            COALESCE(
                NULLIF(btrim(task.department_label), ''),
                department.name,
                'Без отдела'
            ) AS department,
            candidate.task_type,
            candidate.complaint_basis,
            candidate.complaint_evidence,
            task.title,
            task.description,
            task.priority,
            candidate.call_id
        FROM confirmed_tasks AS task
        JOIN task_candidates AS candidate
            ON candidate.id = task.candidate_id
        JOIN operators AS operator
            ON operator.id = candidate.operator_id
        LEFT JOIN departments AS department
            ON department.bitrix_department_id = task.department_id
        WHERE task.delivery_status = 'created'
          AND task.bitrix_item_id IS NOT NULL
          AND candidate.complaint_basis IN (
              'explicit_complaint',
              'explicit_negative_feedback'
          )
        ORDER BY task.updated_at DESC, task.id
        """
    ).fetchall()


def list_calls(
    connection: Connection,
    *,
    operator_id: UUID,
) -> list[SourceCallDto]:
    rows = connection.execute(
        """
        SELECT
            call.id,
            call.bitrix_statistic_id AS statistic_id,
            call.operator_id,
            operator.display_name AS operator_name,
            call.call_type,
            call.duration_seconds,
            call.started_at,
            call.phone_masked,
            call.failed_code,
            call.transcript,
            COALESCE(candidate.conversation_title, '') AS conversation_title,
            call.transcription_status::text AS analysis_status,
            call.analysis_requested_at,
            call.transcription_error
        FROM calls AS call
        JOIN operators AS operator ON operator.id = call.operator_id
        LEFT JOIN task_candidates AS candidate ON candidate.call_id = call.id
        WHERE call.operator_id = %s
        ORDER BY call.started_at DESC, call.id
        """,
        (operator_id,),
    ).fetchall()
    return [_source_call(row) for row in rows]


def get_call(connection: Connection, call_id: UUID) -> SourceCallDto:
    row = connection.execute(
        """
        SELECT
            call.id,
            call.bitrix_statistic_id AS statistic_id,
            call.operator_id,
            operator.display_name AS operator_name,
            call.call_type,
            call.duration_seconds,
            call.started_at,
            call.phone_masked,
            call.failed_code,
            call.transcript,
            COALESCE(candidate.conversation_title, '') AS conversation_title,
            call.transcription_status::text AS analysis_status,
            call.analysis_requested_at,
            call.transcription_error
        FROM calls AS call
        JOIN operators AS operator ON operator.id = call.operator_id
        LEFT JOIN task_candidates AS candidate ON candidate.call_id = call.id
        WHERE call.id = %s
        """,
        (call_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Call {call_id} not found")
    return _source_call(row)


def request_call_analysis(
    connection: Connection,
    *,
    call_id: UUID,
    actor: SessionUserDto,
) -> SourceCallDto:
    with connection.transaction():
        row = connection.execute(
            """
            SELECT
                call.operator_id,
                call.record_file_id,
                call.transcription_status::text AS analysis_status,
                call.analysis_requested_at,
                EXISTS (
                    SELECT 1
                    FROM task_candidates AS candidate
                    WHERE candidate.call_id = call.id
                ) AS has_candidate
            FROM calls AS call
            WHERE call.id = %s
            FOR UPDATE
            """,
            (call_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Call {call_id} not found")
        if actor.role != "supervisor" and row["operator_id"] != actor.id:
            raise PermissionDeniedError(
                "Operator cannot analyze another operator's call"
            )
        if row["record_file_id"] is None:
            raise ConflictError("Call recording is unavailable")
        if row["has_candidate"] or row["analysis_status"] == "completed":
            raise ConflictError("Call is already analyzed")
        if row["analysis_status"] == "processing":
            raise ConflictError("Call analysis is already processing")
        connection.execute(
            """
            UPDATE calls
            SET
                transcription_status = 'pending',
                transcription_error = NULL,
                analysis_requested_at = now(),
                analysis_requested_by_operator_id = %s
            WHERE id = %s
            """,
            (actor.id, call_id),
        )

    return get_call(connection, call_id)


def delete_call(
    connection: Connection,
    *,
    call_id: UUID,
    actor: SessionUserDto,
) -> None:
    """Remove a call and all local derived data, while preventing re-import."""

    with connection.transaction():
        row = connection.execute(
            """
            SELECT operator_id, bitrix_statistic_id
            FROM calls
            WHERE id = %s
            FOR UPDATE
            """,
            (call_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Call {call_id} not found")
        if actor.role != "supervisor" and row["operator_id"] != actor.id:
            raise PermissionDeniedError(
                "Operator cannot delete another operator's call"
            )
        connection.execute(
            """
            INSERT INTO deleted_calls (
                bitrix_statistic_id,
                deleted_by_operator_id
            )
            VALUES (%s, %s)
            ON CONFLICT (bitrix_statistic_id) DO UPDATE SET
                deleted_by_operator_id = EXCLUDED.deleted_by_operator_id,
                deleted_at = now()
            """,
            (row["bitrix_statistic_id"], actor.id),
        )
        connection.execute(
            "DELETE FROM calls WHERE id = %s",
            (call_id,),
        )


def list_candidates(
    connection: Connection,
    *,
    operator_id: UUID | None = None,
) -> list[TaskCandidateDto]:
    params: tuple[Any, ...] = ()
    conditions: list[str] = []
    if operator_id is not None:
        conditions.append("feed.operator_id = %s")
        params = (operator_id,)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    rows = connection.execute(
        f"""
        SELECT
            feed.*,
            operator.display_name AS operator_name,
            call.bitrix_statistic_id AS statistic_id,
            call.call_type,
            call.duration_seconds,
            call.started_at,
            call.phone_masked,
            call.failed_code,
            call.transcript,
            call.transcription_status::text AS analysis_status,
            call.analysis_requested_at
        FROM candidate_feed AS feed
        JOIN operators AS operator ON operator.id = feed.operator_id
        JOIN calls AS call ON call.id = feed.call_id
        {where}
        ORDER BY feed.created_at DESC, feed.id
        """,
        params,
    ).fetchall()
    return [_candidate(row) for row in rows]


def get_candidate(
    connection: Connection,
    candidate_id: UUID,
) -> TaskCandidateDto:
    candidates = _candidate_rows(connection, candidate_id)
    if not candidates:
        raise NotFoundError(f"Candidate {candidate_id} not found")
    return _candidate(candidates[0])


def reject_candidate(
    connection: Connection,
    *,
    candidate_id: UUID,
    actor: SessionUserDto,
    reason: str,
) -> TaskCandidateDto:
    _assert_candidate_access(
        connection,
        candidate_id=candidate_id,
        actor=actor,
    )
    existing = get_candidate(connection, candidate_id)
    if existing.status not in ("pending", "failed"):
        raise ConflictError(f"Candidate is already {existing.status}")

    with connection.transaction():
        if existing.status == "failed":
            connection.execute(
                """
                UPDATE candidate_reviews
                SET
                    decision = 'rejected',
                    decided_by_operator_id = %s,
                    rejection_reason = %s,
                    decided_at = now()
                WHERE candidate_id = %s
                """,
                (actor.id, reason.strip(), candidate_id),
            )
        else:
            connection.execute(
                """
                INSERT INTO candidate_reviews (
                    candidate_id,
                    decision,
                    decided_by_operator_id,
                    rejection_reason
                )
                VALUES (%s, 'rejected', %s, %s)
                """,
                (candidate_id, actor.id, reason.strip()),
            )
    return get_candidate(connection, candidate_id)


def prepare_confirmed_task(
    connection: Connection,
    *,
    candidate_id: UUID,
    actor: SessionUserDto,
    payload: ConfirmCandidatePayload,
    entity_type_id: int,
    retry: bool,
) -> dict[str, Any]:
    _assert_candidate_access(
        connection,
        candidate_id=candidate_id,
        actor=actor,
    )
    candidate = get_candidate(connection, candidate_id)
    expected = "failed" if retry else "pending"
    if candidate.status != expected:
        raise ConflictError(
            f"Candidate must be {expected} for this operation, got {candidate.status}"
        )

    department_row = None
    if payload.department:
        department_row = connection.execute(
            """
            SELECT bitrix_department_id
            FROM departments
            WHERE lower(name) = lower(%s)
              AND active
            ORDER BY bitrix_department_id
            LIMIT 1
            """,
            (payload.department,),
        ).fetchone()

    with connection.transaction():
        if retry:
            row = connection.execute(
                """
                UPDATE confirmed_tasks
                SET
                    initiator_operator_id = %s,
                    title = %s,
                    description = %s,
                    department_id = %s,
                    department_label = %s,
                    priority = %s,
                    delivery_status = 'pending',
                    bitrix_item_id = NULL,
                    failure_reason = NULL
                WHERE candidate_id = %s
                RETURNING id
                """,
                (
                    actor.id,
                    payload.task_name.strip(),
                    payload.task_description.strip(),
                    (
                        department_row["bitrix_department_id"]
                        if department_row
                        else None
                    ),
                    payload.department,
                    payload.priority,
                    candidate_id,
                ),
            ).fetchone()
            if row is None:
                raise ConflictError("Failed candidate has no confirmed task")
        else:
            connection.execute(
                """
                INSERT INTO candidate_reviews (
                    candidate_id,
                    decision,
                    decided_by_operator_id
                )
                VALUES (%s, 'confirmed', %s)
                """,
                (candidate_id, actor.id),
            )
            row = connection.execute(
                """
                INSERT INTO confirmed_tasks (
                    candidate_id,
                    initiator_operator_id,
                    title,
                    description,
                    department_id,
                    department_label,
                    priority,
                    bitrix_entity_type_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    candidate_id,
                    actor.id,
                    payload.task_name.strip(),
                    payload.task_description.strip(),
                    (
                        department_row["bitrix_department_id"]
                        if department_row
                        else None
                    ),
                    payload.department,
                    payload.priority,
                    entity_type_id,
                ),
            ).fetchone()

    return {
        "id": row["id"],
        "candidate_id": candidate_id,
        "call_id": candidate.call_id,
        "title": payload.task_name.strip(),
        "description": payload.task_description.strip(),
        "department": payload.department,
        "priority": payload.priority,
        "initiator_operator_id": actor.id,
    }


def finish_task_attempt(
    connection: Connection,
    *,
    confirmed_task_id: UUID,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any] | None,
    bitrix_item_id: str | int | None,
    error_code: str | None,
    error_message: str | None,
) -> None:
    succeeded = bitrix_item_id is not None
    with connection.transaction():
        connection.execute(
            """
            SELECT id
            FROM confirmed_tasks
            WHERE id = %s
            FOR UPDATE
            """,
            (confirmed_task_id,),
        ).fetchone()
        attempt_no = connection.execute(
            """
            SELECT COALESCE(max(attempt_no), 0) + 1 AS next_attempt
            FROM bitrix_task_attempts
            WHERE confirmed_task_id = %s
            """,
            (confirmed_task_id,),
        ).fetchone()["next_attempt"]
        connection.execute(
            """
            INSERT INTO bitrix_task_attempts (
                confirmed_task_id,
                attempt_no,
                request_payload,
                response_payload,
                succeeded,
                error_code,
                error_message
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                confirmed_task_id,
                attempt_no,
                Jsonb(request_payload),
                Jsonb(response_payload) if response_payload is not None else None,
                succeeded,
                error_code,
                error_message,
            ),
        )
        connection.execute(
            """
            UPDATE confirmed_tasks
            SET
                delivery_status = %s,
                bitrix_item_id = %s,
                failure_reason = %s
            WHERE id = %s
            """,
            (
                "created" if succeeded else "failed",
                str(bitrix_item_id) if succeeded else None,
                None if succeeded else error_message,
                confirmed_task_id,
            ),
        )


def _assert_candidate_access(
    connection: Connection,
    *,
    candidate_id: UUID,
    actor: SessionUserDto,
) -> None:
    row = connection.execute(
        "SELECT operator_id FROM task_candidates WHERE id = %s",
        (candidate_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Candidate {candidate_id} not found")
    if actor.role != "supervisor" and row["operator_id"] != actor.id:
        raise PermissionDeniedError("Operator cannot modify another operator's candidate")


def _candidate_rows(
    connection: Connection,
    candidate_id: UUID,
) -> list[dict[str, Any]]:
    return connection.execute(
        """
        SELECT
            feed.*,
            operator.display_name AS operator_name,
            call.bitrix_statistic_id AS statistic_id,
            call.call_type,
            call.duration_seconds,
            call.started_at,
            call.phone_masked,
            call.failed_code,
            call.transcript,
            call.transcription_status::text AS analysis_status,
            call.analysis_requested_at
        FROM candidate_feed AS feed
        JOIN operators AS operator ON operator.id = feed.operator_id
        JOIN calls AS call ON call.id = feed.call_id
        WHERE feed.id = %s
        """,
        (candidate_id,),
    ).fetchall()


def _candidate(row: dict[str, Any]) -> TaskCandidateDto:
    return TaskCandidateDto(
        id=row["id"],
        call_id=row["call_id"],
        call=_source_call(row),
        operator_id=row["operator_id"],
        operator_name=row["operator_name"],
        conversation_title=row["conversation_title"],
        should_create=row["should_create"],
        task_name=row["task_name"],
        task_description=row["task_description"],
        department=row["department"],
        priority=row["priority"],
        task_type=row["task_type"],
        quality_criterion=row["quality_criterion"],
        complaint_basis=row["complaint_basis"],
        complaint_evidence=row["complaint_evidence"],
        status=row["status"],
        bitrix_task_id=row["bitrix_item_id"],
        failure_reason=row["failure_reason"],
        rejection_reason=row["rejection_reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _source_call(row: dict[str, Any]) -> SourceCallDto:
    call_id = row["call_id"] if "call_id" in row else row["id"]
    return SourceCallDto(
        id=call_id,
        statistic_id=row["statistic_id"],
        operator_id=row["operator_id"],
        operator_name=row["operator_name"],
        direction=_direction(row["call_type"]),
        duration_seconds=row["duration_seconds"],
        started_at=row["started_at"],
        phone_masked=row["phone_masked"],
        failed_code=row["failed_code"],
        transcript=row["transcript"],
        conversation_title=row.get("conversation_title") or "",
        analysis_status=row["analysis_status"],
        analysis_requested=row["analysis_requested_at"] is not None,
        analysis_error=row.get("transcription_error"),
    )


def _direction(call_type: int) -> str:
    return "outbound" if call_type in (1, 4, 5) else "inbound"


def _session_user(row: dict[str, Any], *, source: str) -> SessionUserDto:
    return SessionUserDto(
        id=row["id"],
        display_name=row["display_name"],
        work_position=row["work_position"],
        initials=_initials(row["display_name"]),
        avatar_url="",
        role=row["role"],
        department_ids=list(row["department_ids"]),
        source=source,
    )


def _initials(display_name: str) -> str:
    parts = [part for part in display_name.split() if part]
    return "".join(part[0].upper() for part in parts[:2]) or "?"


__all__ = [
    "ConflictError",
    "NotFoundError",
    "PermissionDeniedError",
    "create_session",
    "delete_call",
    "finish_task_attempt",
    "get_call",
    "get_candidate",
    "get_complaint_analytics",
    "get_operator_by_bitrix_user_id",
    "get_operator_bitrix_user_id",
    "get_operator_by_id",
    "get_session_user",
    "list_calls",
    "list_complaint_export_rows",
    "list_candidates",
    "list_departments",
    "list_emulation_users",
    "list_operator_summaries",
    "prepare_confirmed_task",
    "request_call_analysis",
    "reject_candidate",
]
