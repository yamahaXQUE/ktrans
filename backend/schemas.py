"""HTTP DTOs matching ``frontend/src/types/domain.ts`` exactly."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from backend.task_policy import ComplaintBasis, TaskType


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


UserRole = Literal["operator", "supervisor"]
CandidateStatus = Literal["pending", "confirmed", "rejected", "failed"]
CallDirection = Literal["inbound", "outbound"]
AnalysisStatus = Literal["pending", "processing", "completed", "failed"]


class SessionUserDto(ApiModel):
    id: UUID
    display_name: str
    work_position: str
    initials: str
    avatar_url: str = ""
    role: UserRole
    department_ids: list[int]
    source: Literal["bitrix", "local"]


class SessionDto(ApiModel):
    user: SessionUserDto


class EmulationSessionPayload(ApiModel):
    operator_id: UUID


class DepartmentDto(ApiModel):
    id: int
    name: str


class DictionariesDto(ApiModel):
    departments: list[DepartmentDto]


class SourceCallDto(ApiModel):
    id: UUID
    statistic_id: int
    operator_id: UUID
    operator_name: str
    direction: CallDirection
    duration_seconds: int
    started_at: datetime
    phone_masked: str
    failed_code: str | None
    transcript: str
    conversation_title: str
    analysis_status: AnalysisStatus
    analysis_requested: bool
    analysis_error: str | None = None


class TaskCandidateDto(ApiModel):
    id: UUID
    call_id: UUID
    call: SourceCallDto
    operator_id: UUID
    operator_name: str
    conversation_title: str
    should_create: bool
    task_name: str
    task_description: str
    department: str | None
    priority: int = Field(ge=1, le=5)
    task_type: TaskType | Literal["legacy"]
    quality_criterion: int | None = Field(default=None, ge=1, le=20)
    complaint_basis: ComplaintBasis | Literal["legacy"]
    complaint_evidence: str
    is_concrete_complaint: bool | None = None
    complaint_subject: str = ""
    complaint_issue: str = ""
    status: CandidateStatus
    bitrix_task_id: str | None
    failure_reason: str | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime


class OperatorSummaryDto(ApiModel):
    id: UUID
    display_name: str
    work_position: str
    initials: str
    call_count: int
    pending_count: int
    confirmed_count: int
    failed_count: int
    rejected_count: int
    last_call_at: datetime | None


class ComplaintDepartmentStatDto(ApiModel):
    department: str
    count: int = Field(ge=0)
    share_percent: float = Field(ge=0, le=100)


class ComplaintTaskTypeStatDto(ApiModel):
    task_type: TaskType | Literal["legacy"]
    count: int = Field(ge=0)
    share_percent: float = Field(ge=0, le=100)


class ComplaintDailyStatDto(ApiModel):
    day: date
    calls: int = Field(ge=0)
    analyzed_calls: int = Field(ge=0)
    analysis_failures: int = Field(ge=0)
    complaint_candidates: int = Field(ge=0)
    created_tasks: int = Field(ge=0)


class ComplaintAnalyticsDto(ApiModel):
    total_complaints: int = Field(ge=0)
    total_calls: int = Field(ge=0)
    analyzed_calls: int = Field(ge=0)
    analysis_failed_calls: int = Field(ge=0)
    analysis_pending_calls: int = Field(ge=0)
    manual_queue_calls: int = Field(ge=0)
    complaint_candidates: int = Field(ge=0)
    confirmed_candidates: int = Field(ge=0)
    rejected_candidates: int = Field(ge=0)
    delivery_failed_tasks: int = Field(ge=0)
    analysis_coverage_percent: float = Field(ge=0, le=100)
    delivery_success_percent: float = Field(ge=0, le=100)
    period_start: datetime | None
    period_end: datetime | None
    generated_at: datetime
    departments: list[ComplaintDepartmentStatDto]
    task_types: list[ComplaintTaskTypeStatDto]
    daily: list[ComplaintDailyStatDto]


class ConfirmCandidatePayload(ApiModel):
    task_name: str = Field(min_length=1, max_length=160)
    task_description: str = Field(default="", max_length=2000)
    department_id: int | None = Field(default=None, ge=1)
    department: str | None = Field(default=None, max_length=250)
    priority: int = Field(ge=1, le=5)


class RejectCandidatePayload(ApiModel):
    reason: str = Field(min_length=1, max_length=400)


class BitrixSessionAuth(ApiModel):
    access_token: str = Field(min_length=1)
    refresh_token: str | None = None
    domain: str = Field(min_length=1)
    member_id: str | None = None
    expires_in: int | float | None = None


class BitrixSessionPayload(ApiModel):
    auth: BitrixSessionAuth
    user: dict | None = None


__all__ = [
    "BitrixSessionPayload",
    "ComplaintAnalyticsDto",
    "ComplaintDailyStatDto",
    "ComplaintDepartmentStatDto",
    "ComplaintTaskTypeStatDto",
    "ConfirmCandidatePayload",
    "DepartmentDto",
    "DictionariesDto",
    "EmulationSessionPayload",
    "OperatorSummaryDto",
    "RejectCandidatePayload",
    "SessionDto",
    "SessionUserDto",
    "SourceCallDto",
    "TaskCandidateDto",
]
