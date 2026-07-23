"""Long-running production mirror refresh for Bitrix directory and calls."""

from __future__ import annotations

import os
import signal
import threading
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from backend.db import connect
from backend.sync_bitrix import sync_calls, sync_directory
from bitrix import BitrixClient, BitrixMirror


def main() -> None:
    call_interval = _positive_int("BITRIX_SYNC_INTERVAL_SECONDS", 300)
    directory_interval = _positive_int(
        "BITRIX_DIRECTORY_SYNC_INTERVAL_SECONDS",
        3600,
    )
    lookback_hours = _positive_int("BITRIX_CALL_LOOKBACK_HOURS", 48)
    max_records = _positive_int(
        "BITRIX_SYNC_MAX_RECORDS_PER_OPERATOR",
        1000,
    )

    stopped = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    next_directory_sync = 0.0
    while not stopped.is_set():
        cycle_started = time.monotonic()
        try:
            mirror = BitrixMirror(BitrixClient.from_env())
            with connect() as connection:
                now = datetime.now(timezone.utc)
                if cycle_started >= next_directory_sync:
                    directory_result = sync_directory(mirror, connection)
                    print(
                        {"directory": asdict(directory_result)},
                        flush=True,
                    )
                    next_directory_sync = cycle_started + directory_interval

                call_result = sync_calls(
                    mirror,
                    connection,
                    since=now - timedelta(hours=lookback_hours),
                    until=now,
                    max_records_per_operator=max_records,
                )
                print({"calls": asdict(call_result)}, flush=True)
        except Exception as exc:
            print(
                {
                    "sync_error": type(exc).__name__,
                    "message": str(exc),
                },
                flush=True,
            )

        elapsed = time.monotonic() - cycle_started
        stopped.wait(max(1.0, call_interval - elapsed))


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


if __name__ == "__main__":
    main()
