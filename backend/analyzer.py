"""Call transcription and extraction of task candidates."""

from __future__ import annotations

import json
import os
import re
import ssl
from pathlib import Path
from typing import Any, Optional

from openai import DefaultHttpxClient, OpenAI
from pydantic import BaseModel, Field, model_validator

from backend.task_create import TaskCandidate, TaskId, UserId, task_cand
from backend.task_policy import ComplaintBasis, TaskType, render_task_policy


PROMPT_PATH = Path(__file__).parent / "prompt" / "structuredprompt.json"
DEFAULT_TASK_MODEL = "gpt-5.6-luna"
DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
DEFAULT_TRANSCRIPT_ENHANCEMENT_MODEL = DEFAULT_TASK_MODEL
TRANSCRIPTION_PROMPT = (
    "Телефонный разговор контакт-центра KULIKOV. "
    "Сохраняй исходный язык разговора (русский или кыргызский), имена, "
    "номера заказов, сроки и конкретные обязательства без выдумывания."
)
TRANSCRIPT_ENHANCEMENT_PROMPT = """
Ты — редактор автоматической расшифровки телефонного разговора контакт-центра
KULIKOV. Преврати сырой ASR-текст в связный, естественный и удобный для чтения
диалог. Читаемость и цельность важнее дословности.

Правила:
- сохрани исходный язык каждой реплики (русский или кыргызский);
- восстанови пунктуацию, регистр, абзацы и очевидные границы реплик;
- добавляй метки «Оператор:» и «Клиент:» только когда роль говорящего можно
  уверенно определить из самого текста; иначе разделяй речь абзацами без меток;
- исправляй очевидные ошибки распознавания по контексту, выстраивай естественные
  предложения и при необходимости слегка переформулируй сбивчивую речь;
- сохраняй общий смысл разговора, основные имена, заказы, жалобы, договорённости
  и обязательства, но не обязан воспроизводить каждое слово дословно;
- убирай слова-паразиты, дубли, оговорки и незавершённые повторы;
- не смягчай ругань, если она важна для смысла разговора;
- если фрагмент невозможно разумно восстановить, используй «[неразборчиво]»;
- не добавляй заголовок, резюме, выводы, комментарии редактора или новые факты.

Верни весь разговор целиком в поле transcript.
""".strip()


class TaskAnalysisError(RuntimeError):
    """Raised when the model did not return a usable task prediction."""


class TranscriptEnhancementError(RuntimeError):
    """Raised when the model did not return a readable transcript."""


class _ReadableTranscript(BaseModel):
    transcript: str = Field(
        min_length=1,
        description=(
            "The complete, coherent, human-readable edited transcript. It may "
            "lightly rephrase ASR errors but must not replace the conversation "
            "with a summary."
        ),
    )


class _TaskCandidatePrediction(BaseModel):
    """API schema; converted to the domain dataclass at the boundary."""

    conversation_title: str = Field(
        min_length=1,
        max_length=160,
        description=(
            "A concise neutral title describing the main subject of the "
            "conversation, even when no task is recommended."
        ),
    )
    should_create: bool = Field(
        description=(
            "True only when task_type is one of the approved non-none types."
        )
    )
    decision_basis: ComplaintBasis = Field(
        description=(
            "Explicit customer complaint, explicit negative customer feedback, "
            "or none."
        )
    )
    complaint_evidence: str = Field(
        max_length=500,
        description=(
            "A short quote or exact paraphrase proving the customer's complaint; "
            "empty for none."
        ),
    )
    is_concrete_complaint: bool = Field(
        description=(
            "True only when the customer describes both a specific subject and "
            "a specific failure, defect, or negative incident."
        )
    )
    complaint_subject: str = Field(
        max_length=250,
        description=(
            "The specific product, order, payment, app function, location, "
            "service, or operator behavior complained about; empty when the "
            "complaint is not concrete."
        ),
    )
    complaint_issue: str = Field(
        max_length=500,
        description=(
            "The specific failure, defect, incorrect action, or negative incident; "
            "empty when the complaint is not concrete."
        ),
    )
    requires_unstated_exact_data: bool = Field(
        description=(
            "True when an actionable task would require exact facts absent from "
            "the transcript."
        )
    )
    task_type: TaskType = Field(
        description="Exactly one approved type from the closed task policy."
    )
    quality_criterion: int | None = Field(
        description=(
            "Criterion 1-20 only for operator_quality_violation; otherwise null."
        )
    )
    task_name: str = Field(
        max_length=160,
        description="Short action-oriented task title, or empty for none.",
    )
    task_description: str = Field(
        max_length=2000,
        description="Action, relevant context, deadline and owner if explicitly said."
    )
    department: str | None = Field(
        description="Responsible department if explicitly identifiable."
    )
    priority: int = Field(ge=1, le=5)

    @model_validator(mode="after")
    def validate_closed_policy(self) -> "_TaskCandidatePrediction":
        subject = self.complaint_subject.strip()
        issue = self.complaint_issue.strip()
        if self.decision_basis == "none":
            if self.is_concrete_complaint or subject or issue:
                raise ValueError(
                    "decision_basis=none cannot contain a concrete complaint"
                )
        elif self.is_concrete_complaint:
            if self.decision_basis != "explicit_complaint":
                raise ValueError(
                    "a concrete complaint requires decision_basis=explicit_complaint"
                )
            if not subject or not issue:
                raise ValueError(
                    "a concrete complaint requires a specific subject and issue"
                )
        elif subject or issue:
            raise ValueError(
                "non-concrete feedback requires empty complaint subject and issue"
            )

        if self.task_type == "none":
            if self.should_create:
                raise ValueError("task_type=none requires should_create=false")
            if self.task_name or self.task_description or self.department is not None:
                raise ValueError("task_type=none requires empty task fields")
            if self.priority != 1 or self.quality_criterion is not None:
                raise ValueError(
                    "task_type=none requires priority=1 and no quality criterion"
                )
            if self.decision_basis == "none" and self.complaint_evidence.strip():
                raise ValueError(
                    "decision_basis=none requires empty complaint evidence"
                )
            if (
                self.decision_basis != "none"
                and not self.complaint_evidence.strip()
            ):
                raise ValueError(
                    "an explicit complaint basis requires complaint evidence"
                )
            return self

        if not self.should_create:
            raise ValueError("approved task_type requires should_create=true")
        if self.decision_basis != "explicit_complaint":
            raise ValueError(
                "a task requires an explicit concrete complaint"
            )
        if not self.is_concrete_complaint:
            raise ValueError("a task requires a concrete complaint")
        if not subject or not issue:
            raise ValueError(
                "a task requires a specific complaint subject and issue"
            )
        if not self.complaint_evidence.strip():
            raise ValueError("a task requires complaint evidence")
        if self.requires_unstated_exact_data:
            raise ValueError(
                "a task cannot require exact data absent from the transcript"
            )
        if not self.task_name.strip():
            raise ValueError("approved task_type requires task_name")
        if self.task_type == "operator_quality_violation":
            if self.quality_criterion is None or not 1 <= self.quality_criterion <= 20:
                raise ValueError(
                    "operator_quality_violation requires criterion 1-20"
                )
        elif self.quality_criterion is not None:
            raise ValueError(
                "quality_criterion is only valid for operator_quality_violation"
            )
        return self


class AnalyzeCall:
    """Transcribe a call recording downloaded from Bitrix."""

    def __init__(
        self,
        path: str,
        file: str,
        client: Optional[OpenAI] = None,
        *,
        model: str | None = None,
    ):
        self.path = Path(path)
        self.file = file
        self.client = client or _openai_client()
        self.model = model or os.getenv(
            "OPENAI_TRANSCRIPTION_MODEL",
            DEFAULT_TRANSCRIPTION_MODEL,
        )
        self.text = ""

    @property
    def file_path(self) -> Path:
        return self.path / self.file

    def extract_text(self) -> str:
        """Send the audio file to the transcription API."""

        file_path = self.file_path
        if not file_path.is_file():
            raise FileNotFoundError(f"Call recording not found: {file_path}")

        with file_path.open("rb") as audio_file:
            transcription = self.client.audio.transcriptions.create(
                model=self.model,
                file=audio_file,
                prompt=TRANSCRIPTION_PROMPT,
            )

        self.text = transcription.text
        return self.text

    def llm_call(self) -> str:
        """Backward-compatible name for existing callers."""

        return self.extract_text()

    def __repr__(self) -> str:
        return f"AnalyzeCall(file_path={self.file_path!s})"


class EnhanceTranscript:
    """Make an ASR transcript readable without changing its meaning."""

    def __init__(
        self,
        text: str,
        client: Optional[OpenAI] = None,
        *,
        model: str | None = None,
    ):
        self.text = text
        self.client = client or _openai_client()
        self.model = model or os.getenv(
            "OPENAI_TRANSCRIPT_ENHANCEMENT_MODEL",
            os.getenv("OPENAI_TASK_MODEL", DEFAULT_TRANSCRIPT_ENHANCEMENT_MODEL),
        )

    def enhance(self) -> str:
        """Return the full transcript with readability-only edits."""

        source = self.text.strip()
        if not source:
            raise ValueError("transcript cannot be empty")

        response = self.client.responses.parse(
            model=self.model,
            reasoning={"effort": "none"},
            store=False,
            input=[
                {"role": "system", "content": TRANSCRIPT_ENHANCEMENT_PROMPT},
                {"role": "user", "content": source},
            ],
            text_format=_ReadableTranscript,
        )
        readable = _extract_readable_transcript(response).transcript.strip()
        if not readable:
            raise TranscriptEnhancementError(
                "Model returned an empty readable transcript"
            )
        return readable

    def __repr__(self) -> str:
        return f"EnhanceTranscript(text_length={len(self.text)})"


class AnalyzeText:
    """Extract a typed task prediction from a call transcript."""

    def __init__(
        self,
        text: str,
        client: Optional[OpenAI] = None,
        *,
        call_id: TaskId | None = None,
        initiator: UserId | None = None,
        model: str | None = None,
    ):
        self.text = text
        self.client = client or _openai_client()
        self.call_id = call_id
        self.initiator = initiator
        self.model = model or os.getenv("OPENAI_TASK_MODEL", DEFAULT_TASK_MODEL)

    def analyze(
        self,
        *,
        call_id: TaskId | None = None,
        initiator: UserId | None = None,
    ) -> TaskCandidate:
        """Return a prediction only; this method never creates a CRM task."""

        resolved_call_id = self.call_id if call_id is None else call_id
        if resolved_call_id is None or resolved_call_id == "":
            raise ValueError("call_id is required to identify the source call")

        response = self.client.responses.parse(
            model=self.model,
            reasoning={"effort": "none"},
            store=False,
            input=[
                {"role": "system", "content": _load_system_prompt()},
                {"role": "user", "content": self.text},
            ],
            text_format=_TaskCandidatePrediction,
        )
        prediction = _extract_prediction(response)

        if not _prediction_is_grounded(prediction, self.text):
            return TaskCandidate(
                call_id=resolved_call_id,
                conversation_title=prediction.conversation_title,
                task_name="",
                task_description="",
                department=None,
                initiator=self.initiator if initiator is None else initiator,
                priority=1,
                should_create=False,
                task_type="none",
                quality_criterion=None,
                complaint_basis="none",
                complaint_evidence="",
                is_concrete_complaint=False,
                complaint_subject="",
                complaint_issue="",
                requires_unstated_exact_data=False,
            )

        return TaskCandidate(
            call_id=resolved_call_id,
            conversation_title=prediction.conversation_title,
            task_name=prediction.task_name,
            task_description=prediction.task_description,
            department=prediction.department,
            initiator=self.initiator if initiator is None else initiator,
            priority=prediction.priority,
            should_create=prediction.should_create,
            task_type=prediction.task_type,
            quality_criterion=prediction.quality_criterion,
            complaint_basis=prediction.decision_basis,
            complaint_evidence=prediction.complaint_evidence,
            is_concrete_complaint=prediction.is_concrete_complaint,
            complaint_subject=prediction.complaint_subject,
            complaint_issue=prediction.complaint_issue,
            requires_unstated_exact_data=prediction.requires_unstated_exact_data,
        )

    def __repr__(self) -> str:
        return f"AnalyzeText(text_length={len(self.text)}, call_id={self.call_id!r})"


def _load_system_prompt() -> str:
    with PROMPT_PATH.open(encoding="utf-8") as prompt_file:
        prompt_data = json.load(prompt_file)

    instructions = prompt_data["instructions"]
    mapping = prompt_data.get("output_mapping", {})
    field_rules = "\n".join(f"- {name}: {rule}" for name, rule in mapping.items())
    return (
        f"{instructions}\n\nПравила заполнения полей:\n{field_rules}"
        f"\n\nЗакрытая политика допустимых задач:\n{render_task_policy()}"
    )


def _openai_client() -> OpenAI:
    api_key = _secret_value("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    ca_file = os.getenv("OPENAI_CA_FILE")
    if not ca_file:
        return OpenAI(api_key=api_key)

    ssl_context = ssl.create_default_context()
    try:
        ssl_context.load_verify_locations(cafile=ca_file)
    except OSError as exc:
        raise RuntimeError("Could not load OPENAI_CA_FILE") from exc
    return OpenAI(
        api_key=api_key,
        http_client=DefaultHttpxClient(verify=ssl_context),
    )


def _secret_value(variable: str) -> str:
    file_path = os.getenv(f"{variable}_FILE")
    if file_path:
        try:
            return Path(file_path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"Could not read {variable}_FILE") from exc
    return os.getenv(variable, "").strip()


def _extract_prediction(response: Any) -> _TaskCandidatePrediction:
    parsed = getattr(response, "output_parsed", None)
    if parsed is not None:
        return _TaskCandidatePrediction.model_validate(parsed)

    refusals: list[str] = []
    for output in getattr(response, "output", []):
        for content in getattr(output, "content", []):
            refusal = getattr(content, "refusal", None)
            if refusal:
                refusals.append(str(refusal))

    detail = f": {'; '.join(refusals)}" if refusals else ""
    raise TaskAnalysisError(f"Model returned no task prediction{detail}")


def _extract_readable_transcript(response: Any) -> _ReadableTranscript:
    parsed = getattr(response, "output_parsed", None)
    if parsed is not None:
        return _ReadableTranscript.model_validate(parsed)

    refusals: list[str] = []
    for output in getattr(response, "output", []):
        for content in getattr(output, "content", []):
            refusal = getattr(content, "refusal", None)
            if refusal:
                refusals.append(str(refusal))

    detail = f": {'; '.join(refusals)}" if refusals else ""
    raise TranscriptEnhancementError(
        f"Model returned no readable transcript{detail}"
    )


def _prediction_is_grounded(
    prediction: _TaskCandidatePrediction,
    transcript: str,
) -> bool:
    """Require complaint facts to be literal spans from the transcript."""

    normalized_transcript = _normalize_grounding_text(transcript)
    if prediction.decision_basis != "none":
        if not _is_grounded_span(
            prediction.complaint_evidence,
            normalized_transcript,
        ):
            return False
    if prediction.is_concrete_complaint:
        for value in (prediction.complaint_subject, prediction.complaint_issue):
            if not _is_grounded_span(value, normalized_transcript):
                return False
    return True


def _is_grounded_span(value: str, normalized_transcript: str) -> bool:
    normalized_value = _normalize_grounding_text(value)
    return bool(normalized_value) and normalized_value in normalized_transcript


def _normalize_grounding_text(value: str) -> str:
    return " ".join(re.findall(r"[\w]+", value.casefold(), flags=re.UNICODE))


# Compatibility aliases for code written against the prototype.
analyzee_call = AnalyzeCall
analyzee_text = AnalyzeText


__all__ = [
    "AnalyzeCall",
    "AnalyzeText",
    "EnhanceTranscript",
    "DEFAULT_TASK_MODEL",
    "DEFAULT_TRANSCRIPT_ENHANCEMENT_MODEL",
    "DEFAULT_TRANSCRIPTION_MODEL",
    "TaskAnalysisError",
    "TranscriptEnhancementError",
    "TaskCandidate",
    "analyzee_call",
    "analyzee_text",
    "task_cand",
]
