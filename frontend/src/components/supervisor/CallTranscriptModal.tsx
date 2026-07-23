import { AlertTriangle, CheckCircle2, X } from "lucide-react";
import { useEffect, useRef } from "react";
import type { SourceCall, TaskCandidate } from "../../types/domain";
import { CallPanel } from "../common/CallPanel";
import { PriorityPill, StatusPill } from "../common/Pills";
import { TASK_TYPE_LABEL } from "../../constants/task";

type CallTranscriptModalProps = {
  call: SourceCall;
  candidate: TaskCandidate | null;
  onClose: () => void;
};

export function CallTranscriptModal({ call, candidate, onClose }: CallTranscriptModalProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeButtonRef.current?.focus();
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const hasTask = Boolean(candidate && candidate.shouldCreate && candidate.taskName.trim());

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section
        className="details-panel form-panel"
        aria-label={`Расшифровка звонка ${call.id}`}
        aria-modal="true"
        role="dialog"
      >
        <div className="view-header details-header">
          <div>
            <h2>Звонок {call.id}</h2>
            <p>{call.operatorName}</p>
          </div>
          <button
            ref={closeButtonRef}
            className="secondary icon-button"
            type="button"
            aria-label="Закрыть"
            title="Закрыть"
            onClick={onClose}
          >
            <X size={17} />
          </button>
        </div>

        {candidate ? (
          <section className="outcome-block">
            <div className="details-status-row">
              <StatusPill status={candidate.status} />
              {candidate.taskType !== "legacy" && (
                <span className="tag">{TASK_TYPE_LABEL[candidate.taskType]}</span>
              )}
              {candidate.qualityCriterion && (
                <span className="tag">Критерий {candidate.qualityCriterion}</span>
              )}
              {hasTask && <PriorityPill priority={candidate.priority} />}
              {candidate.department && <span className="tag">{candidate.department}</span>}
              {candidate.bitrixTaskId && (
                <span className="tag">Bitrix · {candidate.bitrixTaskId}</span>
              )}
            </div>

            {hasTask ? (
              <>
                <span className="field-label">Извлечённая задача</span>
                <p className="outcome-title">{candidate.taskName}</p>
                {candidate.taskDescription && (
                  <p className="outcome-desc">{candidate.taskDescription}</p>
                )}
              </>
            ) : (
              <p className="outcome-desc">
                Модель не выделила задачу из этого звонка
                {candidate.status === "rejected" ? " — кандидат отклонён оператором." : "."}
              </p>
            )}

            {candidate.status === "failed" && candidate.failureReason && (
              <div className="review-alert review-alert-danger">
                <AlertTriangle size={18} />
                <div>
                  <strong>Задача не создалась в Bitrix</strong>
                  <span>{candidate.failureReason}</span>
                </div>
              </div>
            )}

            {candidate.status === "confirmed" && (
              <div className="review-alert review-alert-ok">
                <CheckCircle2 size={18} />
                <div>
                  <strong>Задача создана в Bitrix</strong>
                  <span>{candidate.bitrixTaskId}</span>
                </div>
              </div>
            )}
          </section>
        ) : (
          <div className="review-alert">
            <div>
              <strong>Кандидат ещё не сформирован</strong>
              <span>Для этого звонка нет предсказанной задачи.</span>
            </div>
          </div>
        )}

        <CallPanel call={call} />

        <div className="edit-actions">
          <button type="button" onClick={onClose}>
            Закрыть
          </button>
        </div>
      </section>
    </div>
  );
}
