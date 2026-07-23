"""Apply ordered SQL migrations and verify already-applied checksums."""

from __future__ import annotations

import hashlib
from pathlib import Path

from backend.db import connect


MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"


def migrate() -> list[str]:
    applied_now: list[str] = []
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        raise RuntimeError(f"No migrations found in {MIGRATIONS_DIR}")

    with connect(autocommit=True) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version text PRIMARY KEY,
                checksum char(64) NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        existing = {
            row["version"]: row["checksum"].strip()
            for row in connection.execute(
                "SELECT version, checksum FROM schema_migrations"
            ).fetchall()
        }

        for path in migration_files:
            version = path.stem
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            previous_checksum = existing.get(version)
            if previous_checksum:
                if previous_checksum != checksum:
                    raise RuntimeError(
                        f"Applied migration {version} was modified"
                    )
                continue

            connection.execute(sql)
            connection.execute(
                """
                INSERT INTO schema_migrations (version, checksum)
                VALUES (%s, %s)
                """,
                (version, checksum),
            )
            applied_now.append(version)

    return applied_now


if __name__ == "__main__":
    versions = migrate()
    if versions:
        print(f"Applied migrations: {', '.join(versions)}")
    else:
        print("Database is up to date")
