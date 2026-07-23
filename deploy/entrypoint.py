"""Container startup: wait for PostgreSQL, migrate, then replace with Uvicorn."""

from __future__ import annotations

import os
import sys
import time

from psycopg import OperationalError

from backend.migrate import migrate


def main() -> None:
    timeout = _positive_int("DB_STARTUP_TIMEOUT", default=60)
    deadline = time.monotonic() + timeout
    while True:
        try:
            applied = migrate()
            break
        except OperationalError as exc:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"PostgreSQL was unavailable for {timeout} seconds"
                ) from exc
            print("PostgreSQL is not ready; retrying migration...", flush=True)
            time.sleep(2)

    if applied:
        print(f"Applied migrations: {', '.join(applied)}", flush=True)
    else:
        print("Database is up to date", flush=True)

    port = _positive_int("PORT", default=8080)
    workers = _positive_int("WEB_CONCURRENCY", default=1)
    forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1")
    command = [
        "uvicorn",
        "backend.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        "--workers",
        str(workers),
        "--proxy-headers",
        "--forwarded-allow-ips",
        forwarded_allow_ips,
    ]
    os.execvp(command[0], command)


def _positive_int(name: str, *, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Container startup failed: {exc}", file=sys.stderr, flush=True)
        raise
