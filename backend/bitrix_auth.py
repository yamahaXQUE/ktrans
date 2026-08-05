"""Validate a Bitrix iframe OAuth session without trusting frontend user data."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from bitrix import BitrixClient, BitrixTransportError


DEFAULT_BITRIX_PORTAL = "bitrix.kulikov.com"


@dataclass(frozen=True, slots=True)
class ValidatedBitrixUser:
    id: int
    display_name: str
    work_position: str


def validate_current_user(
    *,
    domain: str,
    access_token: str,
) -> int:
    """Return the authenticated Bitrix user ID after a server-side REST call."""

    return validate_current_user_profile(
        domain=domain,
        access_token=access_token,
    ).id


def validate_current_user_profile(
    *,
    domain: str,
    access_token: str,
) -> ValidatedBitrixUser:
    """Return trusted current-user fields from the allowed Bitrix portal."""

    host = _allowed_host(domain)
    client = BitrixClient(
        f"https://{host}/rest",
        tls_compatibility=_tls_compatibility(),
    )
    result = client.call(
        "user.current",
        {"auth": access_token},
    ).result
    if not isinstance(result, Mapping):
        raise BitrixTransportError("user.current returned a non-object result")
    raw_id = result.get("ID")
    try:
        user_id = int(raw_id)
    except (TypeError, ValueError) as exc:
        raise BitrixTransportError(
            "user.current returned an invalid user ID"
        ) from exc
    if user_id <= 0:
        raise BitrixTransportError("user.current returned an invalid user ID")
    display_name = " ".join(
        part
        for key in ("NAME", "SECOND_NAME", "LAST_NAME")
        if (part := str(result.get(key) or "").strip())
    )
    return ValidatedBitrixUser(
        id=user_id,
        display_name=display_name or f"Bitrix user {user_id}",
        work_position=str(result.get("WORK_POSITION") or "").strip(),
    )


def _allowed_host(domain: str) -> str:
    candidate = domain.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlsplit(candidate)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Invalid Bitrix portal domain")

    host = parsed.hostname.rstrip(".").lower()
    configured = os.getenv(
        "BITRIX_ALLOWED_PORTALS",
        DEFAULT_BITRIX_PORTAL,
    )
    allowed = {
        item.strip().rstrip(".").lower()
        for item in configured.split(",")
        if item.strip()
    }
    if host not in allowed:
        raise ValueError("Bitrix portal is not allowed")
    return host


def _tls_compatibility() -> bool:
    value = os.getenv("BITRIX_TLS_COMPATIBILITY", "false").strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no"}:
        raise RuntimeError("BITRIX_TLS_COMPATIBILITY must be true or false")
    return value in {"true", "1", "yes"}


__all__ = [
    "ValidatedBitrixUser",
    "validate_current_user",
    "validate_current_user_profile",
]
