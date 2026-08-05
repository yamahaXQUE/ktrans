"""Synchronize the scoped Bitrix directory and call metadata into PostgreSQL."""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from psycopg import Connection
from psycopg.types.json import Jsonb

from backend.db import connect
from bitrix import BitrixCall, BitrixClient, BitrixMirror, BitrixUser


DEFAULT_OPERATOR_DEPARTMENT_ID = 82
_SUPERVISOR_POSITION = re.compile(
    r"супервайзер|руководител|начальник|директор|head",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DirectorySyncResult:
    departments: int
    operators: int
    supervisors: int


@dataclass(frozen=True, slots=True)
class CallSyncResult:
    fetched: int
    upserted: int
    skipped_unknown_operator: int


def operator_department_id() -> int:
    raw = os.getenv(
        "BITRIX_OPERATOR_DEPARTMENT_ID",
        str(DEFAULT_OPERATOR_DEPARTMENT_ID),
    )
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("BITRIX_OPERATOR_DEPARTMENT_ID must be an integer") from exc
    if value <= 0:
        raise RuntimeError("BITRIX_OPERATOR_DEPARTMENT_ID must be positive")
    return value


def sync_directory(
    mirror: BitrixMirror,
    connection: Connection,
    *,
    department_id: int | None = None,
) -> DirectorySyncResult:
    scope_department_id = department_id or operator_department_id()
    departments = list(mirror.iter_departments())
    scoped_users = list(
        mirror.iter_users(
            department_id=scope_department_id,
            active_only=True,
        )
    )
    support_department = next(
        (
            department
            for department in departments
            if department.id == scope_department_id
        ),
        None,
    )
    if support_department is None:
        raise RuntimeError(
            f"Bitrix department {scope_department_id} was not returned"
        )

    head_user_id = support_department.head_user_id
    with connection.transaction():
        for department in departments:
            connection.execute(
                """
                INSERT INTO departments (
                    bitrix_department_id,
                    name,
                    parent_bitrix_department_id,
                    head_bitrix_user_id,
                    active,
                    synced_at
                )
                VALUES (%s, %s, %s, %s, true, now())
                ON CONFLICT (bitrix_department_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    parent_bitrix_department_id =
                        EXCLUDED.parent_bitrix_department_id,
                    head_bitrix_user_id = EXCLUDED.head_bitrix_user_id,
                    active = true,
                    synced_at = now()
                """,
                (
                    department.id,
                    department.name,
                    department.parent_id,
                    department.head_user_id,
                ),
            )

        current_department_ids = [department.id for department in departments]
        connection.execute(
            """
            UPDATE departments
            SET active = false, synced_at = now()
            WHERE active
              AND NOT (bitrix_department_id = ANY(%s))
            """,
            (current_department_ids,),
        )

        current_user_ids: list[int] = []
        supervisor_count = 0
        for user in scoped_users:
            role = _operator_role(user, head_user_id)
            if role == "supervisor":
                supervisor_count += 1
            current_user_ids.append(user.id)
            operator_row = connection.execute(
                """
                INSERT INTO operators (
                    bitrix_user_id,
                    display_name,
                    work_position,
                    email,
                    internal_phone,
                    active,
                    role,
                    synced_at
                )
                VALUES (%s, %s, %s, %s, %s, true, %s, now())
                ON CONFLICT (bitrix_user_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    work_position = EXCLUDED.work_position,
                    email = EXCLUDED.email,
                    internal_phone = EXCLUDED.internal_phone,
                    active = true,
                    role = EXCLUDED.role,
                    synced_at = now()
                RETURNING id
                """,
                (
                    user.id,
                    user.display_name,
                    user.work_position,
                    user.email,
                    user.internal_phone,
                    role,
                ),
            ).fetchone()
            operator_uuid = operator_row["id"]
            connection.execute(
                "DELETE FROM operator_departments WHERE operator_id = %s",
                (operator_uuid,),
            )
            for index, user_department_id in enumerate(user.department_ids):
                connection.execute(
                    """
                    INSERT INTO operator_departments (
                        operator_id,
                        department_id,
                        is_primary
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (operator_id, department_id) DO UPDATE SET
                        is_primary = EXCLUDED.is_primary
                    """,
                    (operator_uuid, user_department_id, index == 0),
                )

        if current_user_ids:
            connection.execute(
                """
                UPDATE operators AS operator
                SET active = false, synced_at = now()
                WHERE EXISTS (
                    SELECT 1
                    FROM operator_departments AS membership
                    WHERE membership.operator_id = operator.id
                      AND membership.department_id = %s
                )
                  AND NOT (operator.bitrix_user_id = ANY(%s))
                """,
                (scope_department_id, current_user_ids),
            )

    return DirectorySyncResult(
        departments=len(departments),
        operators=len(scoped_users),
        supervisors=supervisor_count,
    )


def sync_calls(
    mirror: BitrixMirror,
    connection: Connection,
    *,
    since: datetime,
    until: datetime | None = None,
    max_records_per_operator: int | None = None,
) -> CallSyncResult:
    operator_rows = connection.execute(
        """
        SELECT id, bitrix_user_id
        FROM operators
        WHERE active
        """
    ).fetchall()
    operator_ids = {
        int(row["bitrix_user_id"]): row["id"]
        for row in operator_rows
    }

    fetched = 0
    upserted = 0
    skipped = 0
    with connection.transaction():
        for bitrix_user_id in operator_ids:
            calls = mirror.iter_calls(
                since=since,
                until=until,
                portal_user_id=bitrix_user_id,
                max_records=max_records_per_operator,
            )
            for call in calls:
                fetched += 1
                if call.portal_user_id not in operator_ids:
                    skipped += 1
                    continue
                _upsert_call(
                    connection,
                    operator_ids[call.portal_user_id],
                    call,
                )
                upserted += 1

    return CallSyncResult(
        fetched=fetched,
        upserted=upserted,
        skipped_unknown_operator=skipped,
    )


def _upsert_call(
    connection: Connection,
    operator_uuid: object,
    call: BitrixCall,
) -> None:
    raw_payload = asdict(call)
    raw_payload["started_at"] = call.started_at.isoformat()
    connection.execute(
        """
        INSERT INTO calls (
            bitrix_statistic_id,
            bitrix_call_id,
            operator_id,
            call_type,
            duration_seconds,
            started_at,
            phone_number,
            phone_masked,
            failed_code,
            crm_entity_type,
            crm_entity_id,
            crm_activity_id,
            record_file_id,
            raw_payload,
            synced_at
        )
        SELECT
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, now()
        WHERE NOT EXISTS (
            SELECT 1
            FROM deleted_calls
            WHERE bitrix_statistic_id = %s
        )
        ON CONFLICT (bitrix_statistic_id) DO UPDATE SET
            bitrix_call_id = EXCLUDED.bitrix_call_id,
            operator_id = EXCLUDED.operator_id,
            call_type = EXCLUDED.call_type,
            duration_seconds = EXCLUDED.duration_seconds,
            started_at = EXCLUDED.started_at,
            phone_number = EXCLUDED.phone_number,
            phone_masked = EXCLUDED.phone_masked,
            failed_code = EXCLUDED.failed_code,
            crm_entity_type = EXCLUDED.crm_entity_type,
            crm_entity_id = EXCLUDED.crm_entity_id,
            crm_activity_id = EXCLUDED.crm_activity_id,
            record_file_id = EXCLUDED.record_file_id,
            raw_payload = EXCLUDED.raw_payload,
            synced_at = now()
        """,
        (
            call.statistic_id,
            call.call_id,
            operator_uuid,
            call.direction,
            call.duration_seconds,
            call.started_at,
            call.phone_number,
            mask_phone(call.phone_number),
            call.failed_code,
            call.crm_entity_type,
            call.crm_entity_id,
            call.crm_activity_id,
            call.record_file_id,
            Jsonb(raw_payload),
            call.statistic_id,
        ),
    )


def mask_phone(phone: str | None) -> str:
    if not phone:
        return ""
    digits = "".join(character for character in phone if character.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits)
    prefix = f"+{digits[:3]}" if phone.strip().startswith("+") else digits[:3]
    return f"{prefix} {'X' * max(3, len(digits) - 7)} {digits[-4:]}"


def _operator_role(user: BitrixUser, head_user_id: int | None) -> str:
    if head_user_id is not None and user.id == head_user_id:
        return "supervisor"
    if _SUPERVISOR_POSITION.search(user.work_position):
        return "supervisor"
    return "operator"


def _build_mirror() -> BitrixMirror:
    return BitrixMirror(BitrixClient.from_env())


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "resource",
        choices=("directory", "calls", "all"),
    )
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--max-records-per-operator", type=int)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.days <= 0:
        parser.error("--days must be positive")

    mirror = _build_mirror()
    with connect() as connection:
        if args.resource in ("directory", "all"):
            print(asdict(sync_directory(mirror, connection)))
        if args.resource in ("calls", "all"):
            since = datetime.now(timezone.utc) - timedelta(days=args.days)
            print(
                asdict(
                    sync_calls(
                        mirror,
                        connection,
                        since=since,
                        max_records_per_operator=args.max_records_per_operator,
                    )
                )
            )


if __name__ == "__main__":
    main()
