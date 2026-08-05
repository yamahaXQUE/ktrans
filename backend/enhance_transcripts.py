"""One-off backfill for transcripts created before the readability pass."""

from __future__ import annotations

import argparse
import os
from dataclasses import asdict, dataclass
from uuid import UUID

from backend.analysis_daemon import _safe_error
from backend.analyzer import (
    DEFAULT_TRANSCRIPT_ENHANCEMENT_MODEL,
    EnhanceTranscript,
    _openai_client,
)
from backend.db import connect


@dataclass(frozen=True, slots=True)
class BackfillResult:
    selected: int
    enhanced: int
    failed: int


def enhance_existing_transcripts(*, limit: int) -> BackfillResult:
    if limit <= 0:
        raise ValueError("limit must be positive")

    model = os.getenv(
        "OPENAI_TRANSCRIPT_ENHANCEMENT_MODEL",
        os.getenv("OPENAI_TASK_MODEL", DEFAULT_TRANSCRIPT_ENHANCEMENT_MODEL),
    ).strip()
    if not model:
        raise RuntimeError("transcript enhancement model is not configured")

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, raw_transcript
            FROM calls
            WHERE transcription_status = 'completed'
              AND btrim(raw_transcript) <> ''
              AND transcript_enhancement_model IS NULL
            ORDER BY started_at DESC, id
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    if not rows:
        return BackfillResult(selected=0, enhanced=0, failed=0)

    client = _openai_client()
    enhanced = 0
    failed = 0
    for row in rows:
        call_id = UUID(str(row["id"]))
        try:
            transcript = EnhanceTranscript(
                row["raw_transcript"],
                client=client,
                model=model,
            ).enhance()
        except Exception as exc:
            _record_failure(call_id, model=model, error=_safe_error(exc))
            failed += 1
        else:
            _record_success(call_id, model=model, transcript=transcript)
            enhanced += 1
        print(
            {
                "transcript_backfill": {
                    "processed": enhanced + failed,
                    "selected": len(rows),
                    "enhanced": enhanced,
                    "failed": failed,
                }
            },
            flush=True,
        )

    return BackfillResult(
        selected=len(rows),
        enhanced=enhanced,
        failed=failed,
    )


def _record_success(call_id: UUID, *, model: str, transcript: str) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE calls
            SET
                transcript = %s,
                transcript_enhancement_model = %s,
                transcript_enhanced_at = now(),
                transcript_enhancement_error = NULL
            WHERE id = %s
              AND transcript_enhancement_model IS NULL
            """,
            (transcript, model, call_id),
        )


def _record_failure(call_id: UUID, *, model: str, error: str) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE calls
            SET
                transcript_enhancement_model = %s,
                transcript_enhanced_at = NULL,
                transcript_enhancement_error = %s
            WHERE id = %s
              AND transcript_enhancement_model IS NULL
            """,
            (model, error, call_id),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    result = enhance_existing_transcripts(limit=args.limit)
    print({"transcript_backfill_complete": asdict(result)}, flush=True)


if __name__ == "__main__":
    main()
