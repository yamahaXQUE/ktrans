"""Persistence boundary between transcription/analysis workers and the API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb

from backend.repository import ConflictError, NotFoundError, get_candidate
from backend.schemas import TaskCandidateDto
from backend.task_create import TaskCandidate


def persist_call_analysis(
    connection: Connection,
    *,
    call_id: UUID,
    transcript: str,
    raw_transcript: str | None = None,
    transcript_enhancement_model: str | None = None,
    transcript_enhancement_error: str | None = None,
    candidate: TaskCandidate,
    prediction_model: str,
    raw_prediction: dict[str, Any] | None = None,
) -> TaskCandidateDto:
    """Atomically store call text and one immutable prediction for the call."""

    cleaned_transcript = transcript.strip()
    cleaned_raw_transcript = (raw_transcript or transcript).strip()
    if not cleaned_transcript:
        raise ValueError("transcript cannot be empty")
    if not cleaned_raw_transcript:
        raise ValueError("raw_transcript cannot be empty")
    if not prediction_model.strip():
        raise ValueError("prediction_model cannot be empty")
    if str(candidate.call_id) != str(call_id):
        raise ValueError("candidate.call_id does not match call_id")

    with connection.transaction():
        call_row = connection.execute(
            """
            UPDATE calls
            SET
                transcript = %s,
                raw_transcript = %s,
                transcript_enhancement_model = %s,
                transcript_enhancement_error = %s,
                transcript_enhanced_at = CASE
                    WHEN %s::text IS NULL THEN now()
                    ELSE NULL
                END,
                transcription_status = 'completed',
                transcription_error = NULL,
                transcribed_at = now()
            WHERE id = %s
            RETURNING operator_id
            """,
            (
                cleaned_transcript,
                cleaned_raw_transcript,
                transcript_enhancement_model,
                transcript_enhancement_error,
                transcript_enhancement_error,
                call_id,
            ),
        ).fetchone()
        if call_row is None:
            raise NotFoundError(f"Call {call_id} not found")

        department_id = None
        if candidate.department:
            department = connection.execute(
                """
                SELECT bitrix_department_id
                FROM departments
                WHERE active
                  AND lower(name) = lower(%s)
                ORDER BY bitrix_department_id
                LIMIT 1
                """,
                (candidate.department,),
            ).fetchone()
            if department:
                department_id = department["bitrix_department_id"]

        inserted = connection.execute(
            """
            INSERT INTO task_candidates (
                call_id,
                operator_id,
                conversation_title,
                should_create,
                task_name,
                task_description,
                predicted_department_id,
                predicted_department,
                priority,
                task_type,
                quality_criterion,
                complaint_basis,
                complaint_evidence,
                is_concrete_complaint,
                complaint_subject,
                complaint_issue,
                prediction_model,
                raw_prediction
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s
            )
            ON CONFLICT (call_id) DO NOTHING
            RETURNING id
            """,
            (
                call_id,
                call_row["operator_id"],
                candidate.conversation_title,
                candidate.should_create,
                candidate.task_name,
                candidate.task_description,
                department_id,
                candidate.department,
                candidate.priority,
                candidate.task_type,
                candidate.quality_criterion,
                candidate.complaint_basis,
                candidate.complaint_evidence,
                candidate.is_concrete_complaint,
                candidate.complaint_subject,
                candidate.complaint_issue,
                prediction_model.strip(),
                Jsonb(raw_prediction or {}),
            ),
        ).fetchone()
        if inserted is None:
            raise ConflictError(f"Call {call_id} already has a prediction")

    return get_candidate(connection, inserted["id"])


def mark_transcription_failed(
    connection: Connection,
    *,
    call_id: UUID,
    error: str,
) -> None:
    message = error.strip()
    if not message:
        raise ValueError("error cannot be empty")
    row = connection.execute(
        """
        UPDATE calls
        SET
            transcription_status = 'failed',
            transcription_error = %s,
            transcribed_at = NULL
        WHERE id = %s
        RETURNING id
        """,
        (message, call_id),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Call {call_id} not found")


__all__ = ["mark_transcription_failed", "persist_call_analysis"]
