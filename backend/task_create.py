"""Domain objects for the operator-controlled task creation flow.

The model produces :class:`TaskCandidate`.  A candidate is never sent to
Bitrix directly: an operator either turns it into :class:`ConfirmedTask` (and
may edit every task field) or rejects it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from backend.task_policy import ALLOWED_TASK_TYPES


TaskId = str | int
UserId = str | int
_UNSET = object()


@dataclass(frozen=True, slots=True, init=False)
class TaskCandidate:
    """A prediction extracted from one call, not a task in the CRM.

    The custom initializer accepts the old ``task_cand`` field names as well
    as the normalized names.  This keeps existing callers working while the
    serialized dataclass has an unambiguous ``call_id``.
    """

    call_id: TaskId
    conversation_title: str
    task_name: str
    task_description: str
    department: str | None
    initiator: UserId | None
    priority: int
    should_create: bool
    task_type: str
    quality_criterion: int | None
    complaint_basis: str
    complaint_evidence: str
    is_concrete_complaint: bool | None
    complaint_subject: str
    complaint_issue: str
    requires_unstated_exact_data: bool

    def __init__(
        self,
        task_id: TaskId | None = None,
        task_name: str = "",
        department: str | None = None,
        iniciator: UserId | None = None,
        task_text_body: str = "",
        should_create: bool = True,
        priority: int = 3,
        *,
        call_id: TaskId | None = None,
        task_description: str | None = None,
        initiator: UserId | None = None,
        conversation_title: str | None = None,
        task_type: str | None = None,
        quality_criterion: int | None = None,
        complaint_basis: str | None = None,
        complaint_evidence: str = "",
        is_concrete_complaint: bool | None = None,
        complaint_subject: str = "",
        complaint_issue: str = "",
        requires_unstated_exact_data: bool = False,
    ) -> None:
        resolved_call_id = call_id if call_id is not None else task_id
        if resolved_call_id is None or resolved_call_id == "":
            raise ValueError("call_id is required")

        resolved_description = (
            task_description if task_description is not None else task_text_body
        )
        resolved_initiator = initiator if initiator is not None else iniciator
        resolved_conversation_title = (
            conversation_title or task_name or "Разговор с клиентом"
        ).strip()
        if not resolved_conversation_title:
            raise ValueError("conversation_title is required")
        if len(resolved_conversation_title) > 160:
            raise ValueError("conversation_title must be at most 160 characters")

        if not isinstance(should_create, bool):
            raise TypeError("should_create must be bool")
        _validate_priority(priority)
        if should_create and not task_name.strip():
            raise ValueError("task_name is required when should_create is true")
        resolved_task_type = task_type or ("legacy" if should_create else "none")
        resolved_complaint_basis = complaint_basis or (
            "legacy" if should_create else "none"
        )
        cleaned_complaint_evidence = complaint_evidence.strip()
        cleaned_complaint_subject = complaint_subject.strip()
        cleaned_complaint_issue = complaint_issue.strip()
        if resolved_task_type not in ALLOWED_TASK_TYPES:
            raise ValueError(f"unsupported task_type: {resolved_task_type}")
        if resolved_complaint_basis not in {
            "legacy",
            "explicit_complaint",
            "explicit_negative_feedback",
            "none",
        }:
            raise ValueError(
                f"unsupported complaint_basis: {resolved_complaint_basis}"
            )
        if is_concrete_complaint is True:
            if resolved_complaint_basis != "explicit_complaint":
                raise ValueError(
                    "a concrete complaint requires explicit_complaint"
                )
            if not cleaned_complaint_subject or not cleaned_complaint_issue:
                raise ValueError(
                    "a concrete complaint requires a subject and issue"
                )
        elif cleaned_complaint_subject or cleaned_complaint_issue:
            raise ValueError(
                "non-concrete feedback requires empty complaint subject and issue"
            )
        if resolved_task_type == "none" and should_create:
            raise ValueError("task_type=none requires should_create=false")
        if resolved_task_type not in {"none", "legacy"} and not should_create:
            raise ValueError("a classified task_type requires should_create=true")
        if quality_criterion is not None and not 1 <= quality_criterion <= 20:
            raise ValueError("quality_criterion must be between 1 and 20")
        if (
            resolved_task_type == "operator_quality_violation"
            and quality_criterion is None
        ):
            raise ValueError(
                "operator_quality_violation requires quality_criterion"
            )
        if (
            resolved_task_type != "operator_quality_violation"
            and quality_criterion is not None
        ):
            raise ValueError(
                "quality_criterion is only valid for operator_quality_violation"
            )
        if resolved_task_type == "none":
            if (
                resolved_complaint_basis == "none"
                and cleaned_complaint_evidence
            ):
                raise ValueError(
                    "complaint_basis=none requires no evidence"
                )
            if (
                resolved_complaint_basis != "none"
                and not cleaned_complaint_evidence
            ):
                raise ValueError(
                    "an explicit complaint basis requires complaint evidence"
                )
        elif resolved_task_type != "legacy":
            if resolved_complaint_basis != "explicit_complaint":
                raise ValueError(
                    "classified tasks require an explicit concrete complaint"
                )
            if is_concrete_complaint is not True:
                raise ValueError("classified tasks require a concrete complaint")
            if not cleaned_complaint_subject or not cleaned_complaint_issue:
                raise ValueError(
                    "classified tasks require a complaint subject and issue"
                )
            if not cleaned_complaint_evidence:
                raise ValueError("classified tasks require complaint evidence")
            if requires_unstated_exact_data:
                raise ValueError(
                    "classified tasks cannot require unstated exact data"
                )

        object.__setattr__(self, "call_id", resolved_call_id)
        object.__setattr__(
            self,
            "conversation_title",
            resolved_conversation_title,
        )
        object.__setattr__(self, "task_name", task_name.strip())
        object.__setattr__(self, "task_description", resolved_description.strip())
        object.__setattr__(self, "department", _clean_optional_text(department))
        object.__setattr__(self, "initiator", resolved_initiator)
        object.__setattr__(self, "priority", priority)
        object.__setattr__(self, "should_create", should_create)
        object.__setattr__(self, "task_type", resolved_task_type)
        object.__setattr__(self, "quality_criterion", quality_criterion)
        object.__setattr__(self, "complaint_basis", resolved_complaint_basis)
        object.__setattr__(
            self,
            "complaint_evidence",
            cleaned_complaint_evidence,
        )
        object.__setattr__(
            self,
            "is_concrete_complaint",
            is_concrete_complaint,
        )
        object.__setattr__(
            self,
            "complaint_subject",
            cleaned_complaint_subject,
        )
        object.__setattr__(self, "complaint_issue", cleaned_complaint_issue)
        object.__setattr__(
            self,
            "requires_unstated_exact_data",
            requires_unstated_exact_data,
        )

    @property
    def task_id(self) -> TaskId:
        return self.call_id

    @property
    def iniciator(self) -> UserId | None:
        return self.initiator

    @property
    def task_text_body(self) -> str:
        return self.task_description


task_cand = TaskCandidate


@dataclass(frozen=True, slots=True)
class ConfirmedTask:
    """A task approved (and possibly edited) by an operator."""

    source_call_id: TaskId
    title: str
    description: str
    department: str | None = None
    initiator: UserId | None = None
    priority: int = 3

    def __post_init__(self) -> None:
        title = self.title.strip()
        if not title:
            raise ValueError("title is required")
        _validate_priority(self.priority)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "description", self.description.strip())
        object.__setattr__(self, "department", _clean_optional_text(self.department))

    @classmethod
    def from_candidate(
        cls,
        candidate: TaskCandidate,
        *,
        title: str | None = None,
        description: str | None = None,
        department: str | None | object = _UNSET,
        initiator: UserId | None | object = _UNSET,
        priority: int | None = None,
    ) -> "ConfirmedTask":
        """Create a separate task entity using optional operator edits."""

        return cls(
            source_call_id=candidate.call_id,
            title=candidate.task_name if title is None else title,
            description=(
                candidate.task_description if description is None else description
            ),
            department=(
                candidate.department
                if department is _UNSET
                else cast(str | None, department)
            ),
            initiator=(
                candidate.initiator
                if initiator is _UNSET
                else cast(UserId | None, initiator)
            ),
            priority=candidate.priority if priority is None else priority,
        )


@dataclass(frozen=True, slots=True)
class RejectedTaskCandidate:
    """The explicit result of an operator pressing “reject task”."""

    source_call_id: TaskId
    reason: str | None = None

    @classmethod
    def from_candidate(
        cls, candidate: TaskCandidate, reason: str | None = None
    ) -> "RejectedTaskCandidate":
        return cls(
            source_call_id=candidate.call_id,
            reason=_clean_optional_text(reason),
        )


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _validate_priority(priority: int) -> None:
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise TypeError("priority must be an integer")
    if not 1 <= priority <= 5:
        raise ValueError("priority must be between 1 and 5")
