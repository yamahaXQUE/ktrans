import {
  AlertTriangle,
  ArrowDownLeft,
  ArrowUpRight,
  CheckCircle2,
  Sparkles,
  Trash2,
} from "lucide-react";
import type { KeyboardEvent } from "react";
import type { TaskCandidate } from "../../types/domain";
import { directionLabel, formatDuration } from "../../utils/format";
import { formatDate } from "../../utils/date";
import { PriorityPill, StatusPill } from "../common/Pills";
import { COMPLAINT_BASIS_LABEL, TASK_TYPE_LABEL } from "../../constants/task";

type CandidateCardProps = {
  candidate: TaskCandidate;
  onOpen: (candidate: TaskCandidate) => void;
  onDelete: (candidate: TaskCandidate) => void;
};

function handleOpenKeyDown(
  event: KeyboardEvent<HTMLDivElement>,
  candidate: TaskCandidate,
  onOpen: (candidate: TaskCandidate) => void,
) {
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }
  event.preventDefault();
  onOpen(candidate);
}

export function CandidateCard({ candidate, onOpen, onDelete }: CandidateCardProps) {
  const DirectionIcon = candidate.call.direction === "inbound" ? ArrowDownLeft : ArrowUpRight;
  const hasTask = candidate.shouldCreate && candidate.taskName.trim().length > 0;
  const title = candidate.conversationTitle;
  const summary =
    candidate.taskDescription.trim() ||
    "Модель не выделила конкретную задачу из этого звонка — проверьте расшифровку.";

  return (
    <article
      className={`promo-card candidate-card is-openable is-${candidate.status}`}
      aria-label={`Кандидат: ${title}`}
    >
      <div
        className="promo-card-click-zone"
        role="button"
        tabIndex={0}
        onClick={() => onOpen(candidate)}
        onKeyDown={(event) => handleOpenKeyDown(event, candidate, onOpen)}
      >
        <div className="promo-top">
          <div>
            <h3>{title}</h3>
            <div className="tag-row">
              <span className="tag">
                {COMPLAINT_BASIS_LABEL[candidate.complaintBasis]}
              </span>
              {candidate.taskType !== "legacy" && (
                <span className="tag">{TASK_TYPE_LABEL[candidate.taskType]}</span>
              )}
              {candidate.qualityCriterion && (
                <span className="tag">Критерий {candidate.qualityCriterion}</span>
              )}
              {candidate.department && <span className="tag">{candidate.department}</span>}
              {hasTask && <PriorityPill priority={candidate.priority} />}
              <StatusPill status={candidate.status} />
            </div>
          </div>
          <span className="date-pill">{formatDate(candidate.call.startedAt)}</span>
        </div>

        <p className="promo-summary">{summary}</p>
        {candidate.complaintEvidence && (
          <p className="promo-summary">
            Основание: {candidate.complaintEvidence}
          </p>
        )}

        {candidate.status === "failed" && candidate.failureReason && (
          <div className="candidate-alert candidate-alert-danger">
            <AlertTriangle size={15} />
            <span>{candidate.failureReason}</span>
          </div>
        )}

        {candidate.status === "confirmed" && candidate.bitrixTaskId && (
          <div className="candidate-alert candidate-alert-ok">
            <CheckCircle2 size={15} />
            <span>Задача создана в Bitrix · {candidate.bitrixTaskId}</span>
          </div>
        )}

        <div className="meta-row">
          <span>
            <DirectionIcon size={13} /> {directionLabel(candidate.call.direction)}
          </span>
          <span>{formatDuration(candidate.call.durationSeconds)}</span>
          <span>Звонок {candidate.callId}</span>
        </div>
      </div>

      <div className="action-row">
        <div className="card-actions-left">
          <button
            className={candidate.status === "pending" ? "" : "secondary"}
            type="button"
            onClick={() => onOpen(candidate)}
          >
            <Sparkles size={16} />
            {candidate.status === "failed"
              ? "Исправить и создать"
              : candidate.status === "pending"
                ? "Создать задачу"
                : "Открыть"}
          </button>
        </div>
        <button
          className="secondary danger-text icon-button"
          type="button"
          title="Удалить запись"
          aria-label={`Удалить запись «${candidate.conversationTitle}»`}
          onClick={() => onDelete(candidate)}
        >
          <Trash2 size={16} />
        </button>
      </div>
    </article>
  );
}
