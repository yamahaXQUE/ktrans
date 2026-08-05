"""Small Bitrix REST adapter for confirmed tasks."""

from __future__ import annotations

import json
import os
import re
import ssl
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

Transport = Callable[[str, Mapping[str, Any], float], Mapping[str, Any]]
_METHOD_NAME = re.compile(r"^[a-z][a-z0-9_.]*$", re.IGNORECASE)


class BitrixError(RuntimeError):
    """Base exception for the Bitrix boundary."""


class BitrixTransportError(BitrixError):
    """The HTTP request failed or returned an unreadable response."""


class BitrixAPIError(BitrixError):
    """Bitrix returned a REST-level error."""

    def __init__(self, code: str, description: str | None = None):
        self.code = code
        self.description = description
        message = f"Bitrix API error {code}"
        if description:
            message = f"{message}: {description}"
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class TaskAddResult:
    task_id: str | int
    task: Mapping[str, Any]
    raw_response: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class BitrixResponse:
    """Normalized response for arbitrary Bitrix REST methods."""

    result: Any
    total: int | None
    next: int | None
    raw_response: Mapping[str, Any]


class BitrixClient:
    """Client for a Bitrix incoming-webhook base URL."""

    def __init__(
        self,
        webhook_url: str,
        *,
        timeout: float = 15.0,
        transport: Transport | None = None,
        tls_compatibility: bool = False,
    ) -> None:
        if not webhook_url or not webhook_url.strip():
            raise ValueError("webhook_url is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._webhook_url = webhook_url.rstrip("/")
        self._webhook_host = urlsplit(self._webhook_url).hostname
        self._timeout = timeout
        self._tls_compatibility = tls_compatibility
        self._transport = transport or partial(
            _post_json,
            tls_compatibility=tls_compatibility,
        )

    @classmethod
    def from_env(
        cls,
        variable: str = "BITRIX_WEBHOOK_URL",
        **kwargs: Any,
    ) -> "BitrixClient":
        """Build a client without ever hard-coding the webhook credential."""

        webhook_url = _secret_value(variable)
        if not webhook_url:
            raise RuntimeError(f"{variable} is not configured")
        if "tls_compatibility" not in kwargs:
            compatibility = os.getenv("BITRIX_TLS_COMPATIBILITY", "false").lower()
            if compatibility not in {"true", "false", "1", "0", "yes", "no"}:
                raise RuntimeError(
                    "BITRIX_TLS_COMPATIBILITY must be true or false"
                )
            kwargs["tls_compatibility"] = compatibility in {"true", "1", "yes"}
        return cls(webhook_url, **kwargs)

    def call(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> BitrixResponse:
        """Call one REST method and normalize errors and pagination metadata."""

        if not _METHOD_NAME.fullmatch(method):
            raise ValueError(f"Invalid Bitrix method name: {method!r}")
        response = self._transport(
            f"{self._webhook_url}/{method}",
            dict(params or {}),
            self._timeout,
        )
        _raise_api_error(response)
        if "result" not in response:
            raise BitrixTransportError("Bitrix response has no result")
        return BitrixResponse(
            result=response["result"],
            total=_optional_int(response.get("total")),
            next=_optional_int(response.get("next")),
            raw_response=dict(response),
        )

    def iter_list(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        max_records: int | None = None,
        max_pages: int = 1_000,
    ) -> Iterator[Mapping[str, Any]]:
        """Iterate over a classic Bitrix list method using its ``next`` offset."""

        if max_records is not None and max_records < 0:
            raise ValueError("max_records cannot be negative")
        if max_pages <= 0:
            raise ValueError("max_pages must be positive")
        if max_records == 0:
            return

        request_params = dict(params or {})
        offset = _optional_int(request_params.get("start")) or 0
        emitted = 0
        seen_offsets: set[int] = set()

        for _ in range(max_pages):
            if offset in seen_offsets:
                raise BitrixTransportError(
                    f"Bitrix repeated pagination offset {offset}"
                )
            seen_offsets.add(offset)
            request_params["start"] = offset
            page = self.call(method, request_params)
            if not isinstance(page.result, list):
                raise BitrixTransportError(
                    f"{method} returned a non-list result"
                )

            for item in page.result:
                if not isinstance(item, Mapping):
                    raise BitrixTransportError(
                        f"{method} returned a non-object list item"
                    )
                yield item
                emitted += 1
                if max_records is not None and emitted >= max_records:
                    return

            if page.next is None:
                return
            offset = page.next

        raise BitrixTransportError(
            f"{method} exceeded pagination safety limit ({max_pages} pages)"
        )

    def tasks_task_add(self, *, fields: Mapping[str, Any]) -> TaskAddResult:
        """Create a native Bitrix task without retrying the write."""

        if not fields:
            raise ValueError("fields cannot be empty")
        response = self.call("tasks.task.add", {"fields": dict(fields)})
        return _parse_task_add_result(response.raw_response)

    def task_item_add(self, *, fields: Mapping[str, Any]) -> TaskAddResult:
        """Create a native task through the legacy method exposed on-premise."""

        if not fields:
            raise ValueError("fields cannot be empty")
        response = self.call("task.item.add", {"fields": dict(fields)})
        task_id = response.result
        if isinstance(task_id, Mapping):
            task_id = task_id.get("id") or task_id.get("ID")
        if task_id is None or task_id == "":
            raise BitrixTransportError("Bitrix response has no created task id")
        return TaskAddResult(
            task_id=task_id,
            task={"id": task_id},
            raw_response=dict(response.raw_response),
        )

    def task_add(
        self,
        *,
        fields: Mapping[str, Any],
        method: str,
    ) -> TaskAddResult:
        if method == "tasks.task.add":
            return self.tasks_task_add(fields=fields)
        if method == "task.item.add":
            return self.task_item_add(fields=fields)
        raise ValueError(f"Unsupported Bitrix task add method: {method}")

    def download_disk_file(
        self,
        file_id: int,
        destination_directory: str | Path,
        *,
        max_bytes: int = 25 * 1024 * 1024,
    ) -> Path:
        """Download one Bitrix Disk recording without exposing its signed URL."""

        if isinstance(file_id, bool) or not isinstance(file_id, int) or file_id <= 0:
            raise ValueError("file_id must be a positive integer")
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")

        result = self.call("disk.file.get", {"id": file_id}).result
        if not isinstance(result, Mapping):
            raise BitrixTransportError("disk.file.get returned a non-object result")

        raw_url = str(result.get("DOWNLOAD_URL") or "").strip()
        if not raw_url:
            raise BitrixTransportError("Bitrix disk file has no download URL")
        parsed_url = urlsplit(raw_url)
        if (
            parsed_url.scheme != "https"
            or not parsed_url.hostname
            or parsed_url.hostname != self._webhook_host
        ):
            raise BitrixTransportError("Bitrix returned an unsafe download URL")

        declared_size = _optional_int(result.get("SIZE"))
        if declared_size is not None and declared_size > max_bytes:
            raise BitrixTransportError("Bitrix recording exceeds the upload limit")

        suffix = Path(str(result.get("NAME") or "")).suffix.lower()
        if suffix not in {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}:
            suffix = ".mp3"
        destination = Path(destination_directory) / f"recording{suffix}"
        _download_binary(
            raw_url,
            destination,
            timeout=self._timeout,
            max_bytes=max_bytes,
            allowed_host=self._webhook_host,
            tls_compatibility=self._tls_compatibility,
        )
        return destination


def _post_json(
    url: str,
    payload: Mapping[str, Any],
    timeout: float,
    *,
    tls_compatibility: bool = False,
) -> Mapping[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    ssl_context = _bitrix_ssl_context(tls_compatibility)

    try:
        with urlopen(  # noqa: S310
            request,
            timeout=timeout,
            context=ssl_context,
        ) as response:
            response_body = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            error_response = json.loads(detail)
        except json.JSONDecodeError:
            error_response = None
        if isinstance(error_response, Mapping) and error_response.get("error"):
            raise BitrixAPIError(
                str(error_response["error"]),
                _optional_string(error_response.get("error_description")),
            ) from exc
        raise BitrixTransportError(f"Bitrix HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise BitrixTransportError(f"Could not reach Bitrix: {exc.reason}") from exc

    try:
        decoded = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BitrixTransportError("Bitrix returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise BitrixTransportError("Bitrix returned a non-object JSON response")
    return decoded


def _download_binary(
    url: str,
    destination: Path,
    *,
    timeout: float,
    max_bytes: int,
    allowed_host: str | None,
    tls_compatibility: bool,
) -> None:
    request = Request(url, method="GET")
    try:
        with urlopen(  # noqa: S310
            request,
            timeout=timeout,
            context=_bitrix_ssl_context(tls_compatibility),
        ) as response:
            if urlsplit(response.geturl()).hostname != allowed_host:
                raise BitrixTransportError("Bitrix redirected to an unsafe host")
            content_length = _optional_int(response.headers.get("Content-Length"))
            if content_length is not None and content_length > max_bytes:
                raise BitrixTransportError("Bitrix recording exceeds the upload limit")

            written = 0
            with destination.open("wb") as output:
                while chunk := response.read(64 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise BitrixTransportError(
                            "Bitrix recording exceeds the upload limit"
                        )
                    output.write(chunk)
    except HTTPError as exc:
        raise BitrixTransportError(
            f"Bitrix recording download returned HTTP {exc.code}"
        ) from exc
    except URLError as exc:
        raise BitrixTransportError(
            f"Could not download Bitrix recording: {exc.reason}"
        ) from exc
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _bitrix_ssl_context(tls_compatibility: bool) -> ssl.SSLContext | None:
    ca_file = os.getenv("BITRIX_CA_FILE")
    if not tls_compatibility and not ca_file:
        return None

    ssl_context = ssl.create_default_context()
    if ca_file:
        try:
            ssl_context.load_verify_locations(cafile=ca_file)
        except OSError as exc:
            raise BitrixTransportError("Could not load BITRIX_CA_FILE") from exc
    if tls_compatibility:
        strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
        ssl_context.verify_flags &= ~strict_flag
    return ssl_context


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


def _parse_task_add_result(response: Mapping[str, Any]) -> TaskAddResult:
    _raise_api_error(response)
    result = response.get("result")
    if not isinstance(result, Mapping):
        raise BitrixTransportError("Bitrix task response has no result object")

    task_value = result.get("task")
    if isinstance(task_value, Mapping):
        task = dict(task_value)
        task_id = task.get("id") or task.get("ID")
    else:
        task = {}
        task_id = result.get("id") or result.get("ID")
    if task_id is None or task_id == "":
        raise BitrixTransportError("Bitrix response has no created task id")
    return TaskAddResult(
        task_id=task_id,
        task=task,
        raw_response=dict(response),
    )


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise BitrixTransportError(
            f"Bitrix returned invalid pagination metadata: {value!r}"
        ) from exc


def _raise_api_error(response: Mapping[str, Any]) -> None:
    error = response.get("error")
    if error:
        raise BitrixAPIError(
            str(error),
            _optional_string(response.get("error_description")),
        )


__all__ = [
    "BitrixAPIError",
    "BitrixClient",
    "BitrixError",
    "BitrixTransportError",
    "BitrixResponse",
    "TaskAddResult",
]
