"""PostgreSQL connection helpers."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row


def database_url() -> str:
    value = _secret_value("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is not configured")
    return value


def _secret_value(name: str) -> str | None:
    file_name = os.getenv(f"{name}_FILE")
    if file_name:
        try:
            value = Path(file_name).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"Could not read {name}_FILE") from exc
        if not value:
            raise RuntimeError(f"{name}_FILE is empty")
        return value
    return os.getenv(name)


@contextmanager
def connect(*, autocommit: bool = False) -> Iterator[Connection]:
    with psycopg.connect(
        database_url(),
        autocommit=autocommit,
        row_factory=dict_row,
    ) as connection:
        yield connection


__all__ = ["connect", "database_url"]
