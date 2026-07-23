"""Read-only Bitrix data source for users, departments, and calls.

This module is the replacement boundary for the old temporary mirror.  It
keeps the incoming-webhook credential server-side and exposes typed internal
records instead of passing raw Bitrix payloads to a frontend.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator, Mapping

from bitrix.bit import BitrixClient, BitrixTransportError


@dataclass(frozen=True, slots=True)
class BitrixCapabilities:
    scopes: tuple[str, ...]
    methods: frozenset[str]

    def is_advertised(self, method: str) -> bool:
        """Whether ``methods`` lists the name, not proof it can be executed.

        Bitrix omits some working universal CRM methods from this catalog and
        lists some application-context methods that an incoming webhook still
        cannot execute.
        """

        return method in self.methods


@dataclass(frozen=True, slots=True)
class BitrixUser:
    id: int
    active: bool
    display_name: str
    work_position: str
    email: str | None
    department_ids: tuple[int, ...]
    internal_phone: str | None


@dataclass(frozen=True, slots=True)
class BitrixDepartment:
    id: int
    name: str
    parent_id: int | None
    head_user_id: int | None


@dataclass(frozen=True, slots=True)
class BitrixCall:
    statistic_id: int
    call_id: str
    portal_user_id: int
    phone_number: str | None
    direction: int
    duration_seconds: int
    started_at: datetime
    failed_code: str | None
    crm_entity_type: str | None
    crm_entity_id: int | None
    crm_activity_id: int | None
    record_file_id: int | None
    record_url: str | None


class BitrixMirror:
    """Typed, read-only facade over the REST methods used by this project."""

    def __init__(self, client: BitrixClient):
        self.client = client

    def capabilities(self) -> BitrixCapabilities:
        scopes = self.client.call("scope").result
        methods = self.client.call("methods").result
        if not isinstance(scopes, list) or not isinstance(methods, list):
            raise BitrixTransportError("Bitrix returned invalid capability data")
        return BitrixCapabilities(
            scopes=tuple(str(scope) for scope in scopes),
            methods=frozenset(str(method) for method in methods),
        )

    def iter_users(
        self,
        *,
        active_only: bool = True,
        department_id: int | None = None,
        max_records: int | None = None,
    ) -> Iterator[BitrixUser]:
        params: dict[str, Any] = {}
        if active_only:
            params["ACTIVE"] = True
        if department_id is not None:
            params["UF_DEPARTMENT"] = department_id

        for raw in self.client.iter_list(
            "user.get",
            params,
            max_records=max_records,
        ):
            yield _parse_user(raw)

    def iter_departments(
        self,
        *,
        max_records: int | None = None,
    ) -> Iterator[BitrixDepartment]:
        params = {"sort": "ID", "order": "ASC"}
        for raw in self.client.iter_list(
            "department.get",
            params,
            max_records=max_records,
        ):
            yield _parse_department(raw)

    def iter_calls(
        self,
        *,
        since: datetime,
        until: datetime | None = None,
        portal_user_id: int | None = None,
        max_records: int | None = None,
    ) -> Iterator[BitrixCall]:
        """Read a bounded call-history interval.

        Recording URLs and phone numbers are credentials/PII-like data and
        should remain inside the backend.  Frontend DTOs must omit or mask them.
        """

        _require_timezone(since, "since")
        filters: dict[str, Any] = {
            ">=CALL_START_DATE": since.isoformat(timespec="seconds"),
        }
        if until is not None:
            _require_timezone(until, "until")
            if until < since:
                raise ValueError("until cannot be earlier than since")
            filters["<=CALL_START_DATE"] = until.isoformat(timespec="seconds")
        if portal_user_id is not None:
            filters["PORTAL_USER_ID"] = portal_user_id

        params = {
            "FILTER": filters,
            "SORT": "CALL_START_DATE",
            "ORDER": "DESC",
        }
        for raw in self.client.iter_list(
            "voximplant.statistic.get",
            params,
            max_records=max_records,
        ):
            yield _parse_call(raw)


def _parse_user(raw: Mapping[str, Any]) -> BitrixUser:
    display_name = " ".join(
        part.strip()
        for key in ("NAME", "SECOND_NAME", "LAST_NAME")
        if (part := str(raw.get(key) or "")).strip()
    )
    return BitrixUser(
        id=_required_int(raw, "ID"),
        active=_bitrix_bool(raw.get("ACTIVE")),
        display_name=display_name,
        work_position=str(raw.get("WORK_POSITION") or "").strip(),
        email=_optional_text(raw.get("EMAIL")),
        department_ids=tuple(
            _coerce_int(value, "UF_DEPARTMENT")
            for value in _as_list(raw.get("UF_DEPARTMENT"))
        ),
        internal_phone=_optional_text(raw.get("UF_PHONE_INNER")),
    )


def _parse_department(raw: Mapping[str, Any]) -> BitrixDepartment:
    return BitrixDepartment(
        id=_required_int(raw, "ID"),
        name=str(raw.get("NAME") or "").strip(),
        parent_id=_optional_int(raw.get("PARENT"), "PARENT"),
        head_user_id=_optional_int(raw.get("UF_HEAD"), "UF_HEAD"),
    )


def _parse_call(raw: Mapping[str, Any]) -> BitrixCall:
    started_at_text = str(raw.get("CALL_START_DATE") or "")
    try:
        started_at = datetime.fromisoformat(started_at_text)
    except ValueError as exc:
        raise BitrixTransportError(
            f"Invalid CALL_START_DATE: {started_at_text!r}"
        ) from exc
    _require_timezone(started_at, "CALL_START_DATE")

    return BitrixCall(
        statistic_id=_required_int(raw, "ID"),
        call_id=str(raw.get("CALL_ID") or ""),
        portal_user_id=_required_int(raw, "PORTAL_USER_ID"),
        phone_number=_optional_text(raw.get("PHONE_NUMBER")),
        direction=_required_int(raw, "CALL_TYPE"),
        duration_seconds=_required_int(raw, "CALL_DURATION"),
        started_at=started_at,
        failed_code=_optional_text(raw.get("CALL_FAILED_CODE")),
        crm_entity_type=_optional_text(raw.get("CRM_ENTITY_TYPE")),
        crm_entity_id=_optional_int(raw.get("CRM_ENTITY_ID"), "CRM_ENTITY_ID"),
        crm_activity_id=_optional_int(
            raw.get("CRM_ACTIVITY_ID"), "CRM_ACTIVITY_ID"
        ),
        record_file_id=_optional_int(raw.get("RECORD_FILE_ID"), "RECORD_FILE_ID"),
        record_url=_optional_text(raw.get("CALL_RECORD_URL")),
    )


def _required_int(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    if value is None or value == "":
        raise BitrixTransportError(f"Bitrix response is missing {key}")
    return _coerce_int(value, key)


def _optional_int(value: Any, key: str) -> int | None:
    if value is None or value == "":
        return None
    return _coerce_int(value, key)


def _coerce_int(value: Any, key: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise BitrixTransportError(f"Invalid {key}: {value!r}") from exc


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def _bitrix_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in ("Y", "1", 1):
        return True
    if value in ("N", "0", 0, None, ""):
        return False
    raise BitrixTransportError(f"Invalid Bitrix boolean: {value!r}")


def _require_timezone(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


__all__ = [
    "BitrixCall",
    "BitrixCapabilities",
    "BitrixDepartment",
    "BitrixMirror",
    "BitrixUser",
]
