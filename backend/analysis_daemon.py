"""Production worker: Bitrix recording -> transcript -> task candidate."""

from __future__ import annotations

import os
import signal
import tempfile
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from openai import OpenAI

from backend.analysis_store import mark_transcription_failed, persist_call_analysis
from backend.analyzer import (
    DEFAULT_TASK_MODEL,
    DEFAULT_TRANSCRIPT_ENHANCEMENT_MODEL,
    DEFAULT_TRANSCRIPTION_MODEL,
    AnalyzeCall,
    AnalyzeText,
    EnhanceTranscript,
)
from backend.db import connect
from bitrix import BitrixClient


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    poll_interval_seconds: int
    lookback_hours: int
    minimum_duration_seconds: int
    maximum_recording_bytes: int
    stale_processing_minutes: int
    automatic_bitrix_user_ids: tuple[int, ...]
    transcription_model: str
    transcript_enhancement_model: str
    task_model: str

    @classmethod
    def from_env(cls) -> "AnalysisConfig":
        return cls(
            poll_interval_seconds=_positive_int(
                "ANALYSIS_POLL_INTERVAL_SECONDS",
                60,
            ),
            lookback_hours=_positive_int("ANALYSIS_LOOKBACK_HOURS", 24),
            minimum_duration_seconds=_positive_int(
                "ANALYSIS_MIN_DURATION_SECONDS",
                10,
            ),
            maximum_recording_bytes=_positive_int(
                "ANALYSIS_MAX_RECORDING_BYTES",
                25_000_000,
            ),
            stale_processing_minutes=_positive_int(
                "ANALYSIS_STALE_PROCESSING_MINUTES",
                30,
            ),
            automatic_bitrix_user_ids=_positive_int_list(
                "ANALYSIS_AUTO_BITRIX_USER_IDS",
            ),
            transcription_model=os.getenv(
                "OPENAI_TRANSCRIPTION_MODEL",
                DEFAULT_TRANSCRIPTION_MODEL,
            ).strip(),
            transcript_enhancement_model=os.getenv(
                "OPENAI_TRANSCRIPT_ENHANCEMENT_MODEL",
                os.getenv("OPENAI_TASK_MODEL", DEFAULT_TRANSCRIPT_ENHANCEMENT_MODEL),
            ).strip(),
            task_model=os.getenv(
                "OPENAI_TASK_MODEL",
                DEFAULT_TASK_MODEL,
            ).strip(),
        )


@dataclass(frozen=True, slots=True)
class AnalysisJob:
    call_id: UUID
    statistic_id: int
    record_file_id: int
    bitrix_user_id: int
    manually_requested: bool


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    call_id: UUID
    statistic_id: int
    completed: bool
    should_create: bool | None = None
    error_type: str | None = None


def process_next_call(
    config: AnalysisConfig,
    *,
    bitrix_client: BitrixClient | None = None,
    openai_client: OpenAI | None = None,
) -> AnalysisResult | None:
    job = _claim_next_call(config)
    if job is None:
        return None

    try:
        bitrix = bitrix_client or BitrixClient.from_env()
        with tempfile.TemporaryDirectory(prefix="call-analysis-") as temporary:
            recording = bitrix.download_disk_file(
                job.record_file_id,
                temporary,
                max_bytes=config.maximum_recording_bytes,
            )
            transcriber = AnalyzeCall(
                str(recording.parent),
                recording.name,
                client=openai_client,
                model=config.transcription_model,
            )
            raw_transcript = transcriber.extract_text().strip()
            if not raw_transcript:
                raise RuntimeError("Transcription API returned empty text")

            transcript, enhancement_error = _enhance_with_fallback(
                raw_transcript,
                client=transcriber.client,
                model=config.transcript_enhancement_model,
            )

            analyzer = AnalyzeText(
                transcript,
                client=transcriber.client,
                call_id=job.call_id,
                initiator=job.bitrix_user_id,
                model=config.task_model,
            )
            candidate = analyzer.analyze()

        with connect() as connection:
            persist_call_analysis(
                connection,
                call_id=job.call_id,
                transcript=transcript,
                raw_transcript=raw_transcript,
                transcript_enhancement_model=config.transcript_enhancement_model,
                transcript_enhancement_error=enhancement_error,
                candidate=candidate,
                prediction_model=config.task_model,
                raw_prediction=_raw_prediction(candidate),
            )
        return AnalysisResult(
            call_id=job.call_id,
            statistic_id=job.statistic_id,
            completed=True,
            should_create=candidate.should_create,
        )
    except Exception as exc:
        with connect() as connection:
            mark_transcription_failed(
                connection,
                call_id=job.call_id,
                error=_safe_error(exc),
            )
        return AnalysisResult(
            call_id=job.call_id,
            statistic_id=job.statistic_id,
            completed=False,
            error_type=type(exc).__name__,
        )


def main() -> None:
    config = AnalysisConfig.from_env()
    _requeue_stale_calls(config.stale_processing_minutes)

    stopped = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    print(
        {
            "analysis_worker": "started",
            "transcription_model": config.transcription_model,
            "transcript_enhancement_model": config.transcript_enhancement_model,
            "task_model": config.task_model,
            "poll_interval_seconds": config.poll_interval_seconds,
            "lookback_hours": config.lookback_hours,
            "automatic_users": len(config.automatic_bitrix_user_ids),
        },
        flush=True,
    )

    while not stopped.is_set():
        result = process_next_call(config)
        if result is not None:
            payload: dict[str, Any] = {
                "call_analysis": {
                    "call_id": str(result.call_id),
                    "statistic_id": result.statistic_id,
                    "completed": result.completed,
                }
            }
            if result.completed:
                payload["call_analysis"]["should_create"] = result.should_create
            else:
                payload["call_analysis"]["error_type"] = result.error_type
            print(payload, flush=True)
        stopped.wait(config.poll_interval_seconds)


def _claim_next_call(config: AnalysisConfig) -> AnalysisJob | None:
    with connect() as connection:
        with connection.transaction():
            row = connection.execute(
                """
                SELECT
                    call.id,
                    call.bitrix_statistic_id,
                    call.record_file_id,
                    call.analysis_requested_at,
                    operator.bitrix_user_id
                FROM calls AS call
                JOIN operators AS operator ON operator.id = call.operator_id
                WHERE call.transcription_status = 'pending'
                  AND call.record_file_id IS NOT NULL
                  AND (
                      (
                          operator.bitrix_user_id = ANY(%s)
                          AND call.duration_seconds >= %s
                          AND call.started_at >= now() - %s
                      )
                      OR call.analysis_requested_at IS NOT NULL
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM task_candidates AS candidate
                      WHERE candidate.call_id = call.id
                  )
                ORDER BY
                    (call.analysis_requested_at IS NOT NULL) DESC,
                    COALESCE(call.analysis_requested_at, call.started_at) DESC,
                    call.id
                FOR UPDATE OF call SKIP LOCKED
                LIMIT 1
                """,
                (
                    list(config.automatic_bitrix_user_ids),
                    config.minimum_duration_seconds,
                    timedelta(hours=config.lookback_hours),
                ),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE calls
                SET
                    transcription_status = 'processing',
                    transcription_error = NULL
                WHERE id = %s
                """,
                (row["id"],),
            )

    return AnalysisJob(
        call_id=row["id"],
        statistic_id=int(row["bitrix_statistic_id"]),
        record_file_id=int(row["record_file_id"]),
        bitrix_user_id=int(row["bitrix_user_id"]),
        manually_requested=row["analysis_requested_at"] is not None,
    )


def _requeue_stale_calls(stale_minutes: int) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE calls
            SET
                transcription_status = 'pending',
                transcription_error = 'Analysis worker restarted after a stale claim'
            WHERE transcription_status = 'processing'
              AND updated_at < now() - %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM task_candidates AS candidate
                  WHERE candidate.call_id = calls.id
              )
            """,
            (timedelta(minutes=stale_minutes),),
        )


def _raw_prediction(candidate: Any) -> dict[str, Any]:
    return {
        "conversation_title": candidate.conversation_title,
        "should_create": candidate.should_create,
        "task_name": candidate.task_name,
        "task_description": candidate.task_description,
        "department": candidate.department,
        "priority": candidate.priority,
        "task_type": candidate.task_type,
        "quality_criterion": candidate.quality_criterion,
        "complaint_basis": candidate.complaint_basis,
        "complaint_evidence": candidate.complaint_evidence,
        "is_concrete_complaint": candidate.is_concrete_complaint,
        "complaint_subject": candidate.complaint_subject,
        "complaint_issue": candidate.complaint_issue,
        "requires_unstated_exact_data": candidate.requires_unstated_exact_data,
    }


def _safe_error(exc: Exception) -> str:
    message = " ".join(str(exc).split())
    return f"{type(exc).__name__}: {message}"[:2000]


def _enhance_with_fallback(
    raw_transcript: str,
    *,
    client: OpenAI,
    model: str,
) -> tuple[str, str | None]:
    """Enhance text without allowing this optional step to fail the job."""

    try:
        return (
            EnhanceTranscript(
                raw_transcript,
                client=client,
                model=model,
            ).enhance(),
            None,
        )
    except Exception as exc:
        return raw_transcript, _safe_error(exc)


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


def _positive_int_list(name: str) -> tuple[int, ...]:
    values: list[int] = []
    for item in os.getenv(name, "").split(","):
        cleaned = item.strip()
        if not cleaned:
            continue
        try:
            value = int(cleaned)
        except ValueError as exc:
            raise RuntimeError(f"{name} must contain integer IDs") from exc
        if value <= 0:
            raise RuntimeError(f"{name} must contain positive IDs")
        if value not in values:
            values.append(value)
    return tuple(values)


if __name__ == "__main__":
    main()
