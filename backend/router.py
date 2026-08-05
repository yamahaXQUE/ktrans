"""Role-aware HTTP API consumed by the React frontend."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date
from uuid import UUID

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from psycopg import Connection

from backend.bitrix_auth import validate_current_user_profile
from backend.analytics_export import build_complaints_workbook
from backend.db import connect
from backend.repository import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    create_session,
    delete_call,
    get_call,
    get_complaint_analytics,
    get_operator_by_bitrix_user_id,
    get_operator_by_id,
    get_session_user,
    list_calls,
    list_complaint_export_rows,
    list_candidates,
    list_departments,
    list_emulation_users,
    list_operator_summaries,
    reject_candidate,
    request_call_analysis,
    upsert_bypass_supervisor,
)
from backend.schemas import (
    BitrixSessionPayload,
    ComplaintAnalyticsDto,
    ConfirmCandidatePayload,
    DictionariesDto,
    EmulationSessionPayload,
    OperatorSummaryDto,
    RejectCandidatePayload,
    SessionDto,
    SessionUserDto,
    SourceCallDto,
    TaskCandidateDto,
)
from backend.task_delivery import deliver_candidate
from bitrix import BitrixError


SESSION_COOKIE = "call_tasks_session"
router = APIRouter(prefix="/api")


def connection_dependency() -> Iterator[Connection]:
    with connect() as connection:
        yield connection


def current_user(
    connection: Connection = Depends(connection_dependency),
    call_tasks_session: str | None = Cookie(default=None),
) -> SessionUserDto:
    if call_tasks_session:
        try:
            session_id = UUID(call_tasks_session)
        except ValueError as exc:
            raise _unauthorized("Invalid session") from exc
        try:
            return get_session_user(connection, session_id)
        except NotFoundError as exc:
            raise _unauthorized(str(exc)) from exc

    dev_user_id = os.getenv("DEV_BITRIX_USER_ID")
    if dev_user_id:
        try:
            return get_operator_by_bitrix_user_id(
                connection,
                int(dev_user_id),
            ).model_copy(update={"source": "local"})
        except (ValueError, NotFoundError) as exc:
            raise _unauthorized("Development user is unavailable") from exc
    raise _unauthorized("Authentication required")


@router.post("/bitrix/session", response_model=SessionDto)
def open_bitrix_session(
    payload: BitrixSessionPayload,
    response: Response,
    connection: Connection = Depends(connection_dependency),
) -> SessionDto:
    try:
        profile = validate_current_user_profile(
            domain=payload.auth.domain,
            access_token=payload.auth.access_token,
        )
        try:
            user = get_operator_by_bitrix_user_id(connection, profile.id)
        except NotFoundError:
            if profile.id not in _access_bypass_user_ids():
                raise
            user = upsert_bypass_supervisor(
                connection,
                bitrix_user_id=profile.id,
                display_name=profile.display_name,
                work_position=profile.work_position or "Служебный просмотр",
            )
    except (ValueError, BitrixError, NotFoundError) as exc:
        raise _unauthorized(str(exc)) from exc

    session_id = create_session(
        connection,
        user.id,
        member_id=payload.auth.member_id,
    )
    _set_session_cookie(response, session_id)
    return SessionDto(user=user)


@router.get("/emulation/users", response_model=list[SessionUserDto])
def emulation_users(
    connection: Connection = Depends(connection_dependency),
) -> list[SessionUserDto]:
    _require_emulation()
    return list_emulation_users(connection)


@router.post("/emulation/session", response_model=SessionDto)
def open_emulation_session(
    payload: EmulationSessionPayload,
    response: Response,
    connection: Connection = Depends(connection_dependency),
) -> SessionDto:
    _require_emulation()
    try:
        user = get_operator_by_id(
            connection,
            payload.operator_id,
            source="local",
        )
    except NotFoundError as exc:
        raise _repository_http_error(exc) from exc

    session_id = create_session(
        connection,
        user.id,
        member_id="direct-browser-emulation",
    )
    _set_session_cookie(response, session_id)
    return SessionDto(user=user)


@router.get("/session", response_model=SessionDto)
def session(user: SessionUserDto = Depends(current_user)) -> SessionDto:
    return SessionDto(user=user)


@router.get("/dictionaries", response_model=DictionariesDto)
def dictionaries(
    connection: Connection = Depends(connection_dependency),
    _user: SessionUserDto = Depends(current_user),
) -> DictionariesDto:
    return DictionariesDto(departments=list_departments(connection))


@router.get("/candidates", response_model=list[TaskCandidateDto])
def candidates(
    operator_id: UUID | None = Query(default=None, alias="operatorId"),
    connection: Connection = Depends(connection_dependency),
    user: SessionUserDto = Depends(current_user),
) -> list[TaskCandidateDto]:
    if user.role == "operator":
        if operator_id is not None and operator_id != user.id:
            raise _forbidden("Operator cannot view another operator's candidates")
        operator_id = user.id
    return list_candidates(connection, operator_id=operator_id)


@router.patch(
    "/candidates/{candidate_id}/confirm",
    response_model=TaskCandidateDto,
)
def confirm(
    candidate_id: UUID,
    payload: ConfirmCandidatePayload,
    connection: Connection = Depends(connection_dependency),
    user: SessionUserDto = Depends(current_user),
) -> TaskCandidateDto:
    return _deliver(
        connection,
        candidate_id=candidate_id,
        payload=payload,
        user=user,
        retry=False,
    )


@router.patch(
    "/candidates/{candidate_id}/retry",
    response_model=TaskCandidateDto,
)
def retry(
    candidate_id: UUID,
    payload: ConfirmCandidatePayload,
    connection: Connection = Depends(connection_dependency),
    user: SessionUserDto = Depends(current_user),
) -> TaskCandidateDto:
    return _deliver(
        connection,
        candidate_id=candidate_id,
        payload=payload,
        user=user,
        retry=True,
    )


@router.patch(
    "/candidates/{candidate_id}/reject",
    response_model=TaskCandidateDto,
)
def reject(
    candidate_id: UUID,
    payload: RejectCandidatePayload,
    connection: Connection = Depends(connection_dependency),
    user: SessionUserDto = Depends(current_user),
) -> TaskCandidateDto:
    try:
        return reject_candidate(
            connection,
            candidate_id=candidate_id,
            actor=user,
            reason=payload.reason,
        )
    except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
        raise _repository_http_error(exc) from exc


@router.get("/operators", response_model=list[OperatorSummaryDto])
def operators(
    connection: Connection = Depends(connection_dependency),
    user: SessionUserDto = Depends(current_user),
) -> list[OperatorSummaryDto]:
    _require_supervisor(user)
    return list_operator_summaries(connection)


@router.get(
    "/analytics/complaints",
    response_model=ComplaintAnalyticsDto,
)
def complaint_analytics(
    connection: Connection = Depends(connection_dependency),
    user: SessionUserDto = Depends(current_user),
) -> ComplaintAnalyticsDto:
    _require_supervisor(user)
    return get_complaint_analytics(connection)


@router.get("/analytics/complaints.xlsx")
def export_complaints(
    connection: Connection = Depends(connection_dependency),
    user: SessionUserDto = Depends(current_user),
) -> Response:
    _require_supervisor(user)
    analytics = get_complaint_analytics(connection)
    content = build_complaints_workbook(
        list_complaint_export_rows(connection),
        analytics,
    )
    filename = f"complaints-{date.today().isoformat()}.xlsx"
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/operators/{operator_id}/calls",
    response_model=list[SourceCallDto],
)
def operator_calls(
    operator_id: UUID,
    connection: Connection = Depends(connection_dependency),
    user: SessionUserDto = Depends(current_user),
) -> list[SourceCallDto]:
    if user.role == "operator" and operator_id != user.id:
        raise _forbidden("Operator cannot view another operator's calls")
    return list_calls(connection, operator_id=operator_id)


@router.get("/calls/{call_id}", response_model=SourceCallDto)
def call(
    call_id: UUID,
    connection: Connection = Depends(connection_dependency),
    user: SessionUserDto = Depends(current_user),
) -> SourceCallDto:
    try:
        source_call = get_call(connection, call_id)
    except NotFoundError as exc:
        raise _repository_http_error(exc) from exc
    if user.role == "operator" and source_call.operator_id != user.id:
        raise _forbidden("Operator cannot view another operator's call")
    return source_call


@router.post("/calls/{call_id}/analysis", response_model=SourceCallDto)
def queue_call_analysis(
    call_id: UUID,
    connection: Connection = Depends(connection_dependency),
    user: SessionUserDto = Depends(current_user),
) -> SourceCallDto:
    try:
        return request_call_analysis(
            connection,
            call_id=call_id,
            actor=user,
        )
    except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
        raise _repository_http_error(exc) from exc


@router.delete("/calls/{call_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_call(
    call_id: UUID,
    connection: Connection = Depends(connection_dependency),
    user: SessionUserDto = Depends(current_user),
) -> Response:
    try:
        delete_call(
            connection,
            call_id=call_id,
            actor=user,
        )
    except (NotFoundError, PermissionDeniedError) as exc:
        raise _repository_http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _deliver(
    connection: Connection,
    *,
    candidate_id: UUID,
    payload: ConfirmCandidatePayload,
    user: SessionUserDto,
    retry: bool,
) -> TaskCandidateDto:
    try:
        return deliver_candidate(
            connection,
            candidate_id=candidate_id,
            actor=user,
            payload=payload,
            retry=retry,
        )
    except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
        raise _repository_http_error(exc) from exc


def _require_supervisor(user: SessionUserDto) -> None:
    if user.role != "supervisor":
        raise _forbidden("Supervisor role required")


def _require_emulation() -> None:
    if not _boolean_env("BITRIX_EMULATION_ENABLED", default=False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


def _access_bypass_user_ids() -> frozenset[int]:
    raw = os.getenv("BITRIX_ACCESS_BYPASS_USER_IDS", "")
    result: set[int] = set()
    for item in raw.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        try:
            user_id = int(candidate)
        except ValueError as exc:
            raise RuntimeError(
                "BITRIX_ACCESS_BYPASS_USER_IDS must contain positive integers"
            ) from exc
        if user_id <= 0:
            raise RuntimeError(
                "BITRIX_ACCESS_BYPASS_USER_IDS must contain positive integers"
            )
        result.add(user_id)
    return frozenset(result)


def _set_session_cookie(response: Response, session_id: UUID) -> None:
    secure = _boolean_env("SESSION_COOKIE_SECURE", default=False)
    response.set_cookie(
        SESSION_COOKIE,
        str(session_id),
        max_age=8 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="none" if secure else "lax",
        path="/",
    )


def _repository_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PermissionDeniedError):
        return _forbidden(str(exc))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)


def _forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def _boolean_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized not in {"true", "false", "1", "0", "yes", "no"}:
        raise RuntimeError(f"{name} must be true or false")
    return normalized in {"true", "1", "yes"}


__all__ = ["router"]
