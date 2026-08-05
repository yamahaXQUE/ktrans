import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  RefreshCw,
  Send,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import type {
  ConfirmCandidatePayload,
  Department,
  Priority,
  TaskCandidate,
} from "../../types/domain";
import {
  PRIORITIES,
  PRIORITY_LABEL,
  REJECTION_REASON_MAX_LENGTH,
  TASK_DESCRIPTION_MAX_LENGTH,
  TASK_NAME_MAX_LENGTH,
} from "../../constants/task";
import { formatDateTime } from "../../utils/date";
import { CallPanel } from "../common/CallPanel";
import { PriorityPill, StatusPill } from "../common/Pills";

type TaskReviewModalProps = {
  candidate: TaskCandidate;
  departments: Department[];
  busy: boolean;
  onClose: () => void;
  onConfirm: (payload: ConfirmCandidatePayload) => void;
  onRetry: (payload: ConfirmCandidatePayload) => void;
  onReject: (reason: string) => void;
  onDelete: () => void;
};

export function TaskReviewModal({
  candidate,
  departments,
  busy,
  onClose,
  onConfirm,
  onRetry,
  onReject,
  onDelete,
}: TaskReviewModalProps) {
  const editable = candidate.status === "pending" || candidate.status === "failed";

  const [taskName, setTaskName] = useState(
    candidate.taskName || candidate.conversationTitle,
  );
  const [taskDescription, setTaskDescription] = useState(candidate.taskDescription);
  const [departmentId, setDepartmentId] = useState<number | null>(() => {
    const matched = departments.find(
      (item) =>
        item.name.toLocaleLowerCase("ru-RU") ===
        candidate.department?.toLocaleLowerCase("ru-RU"),
    );
    return matched?.id ?? null;
  });
  const [priority, setPriority] = useState<Priority>(candidate.priority);
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
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

  const payload = useMemo<ConfirmCandidatePayload>(
    () => {
      const selectedDepartment = departments.find(
        (item) => item.id === departmentId,
      );
      return {
        taskName: taskName.trim(),
        taskDescription: taskDescription.trim(),
        departmentId,
        department: selectedDepartment?.name ?? null,
        priority,
      };
    },
    [departmentId, departments, priority, taskDescription, taskName],
  );

  const canSubmit =
    candidate.shouldCreate &&
    candidate.isConcreteComplaint === true &&
    payload.taskName.length > 0 &&
    !busy;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    if (candidate.status === "failed") {
      onRetry(payload);
    } else {
      onConfirm(payload);
    }
  }

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <form
        className="edit-panel form-panel review-panel"
        aria-label="Разбор звонка"
        aria-modal="true"
        role="dialog"
        onSubmit={handleSubmit}
      >
        <div className="view-header details-header">
          <div>
            <h2>{candidate.conversationTitle}</h2>
            <p>
              {candidate.operatorName} · обновлено {formatDateTime(candidate.updatedAt)}
            </p>
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

        <div className="details-status-row">
          <StatusPill status={candidate.status} />
          <PriorityPill priority={priority} />
          {candidate.isConcreteComplaint !== true && (
            <span className="tag soft">
              Нет конкретной жалобы — создание задачи запрещено
            </span>
          )}
          {candidate.bitrixTaskId && (
            <span className="tag">Bitrix · {candidate.bitrixTaskId}</span>
          )}
        </div>

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
              <strong>Задача создана</strong>
              <span>Кандидат подтверждён и отправлен в Bitrix.</span>
            </div>
          </div>
        )}

        {candidate.status === "rejected" && (
          <div className="review-alert">
            <Ban size={18} />
            <div>
              <strong>Кандидат отклонён</strong>
              <span>{candidate.rejectionReason || "Причина не указана."}</span>
            </div>
          </div>
        )}

        <CallPanel call={candidate.call} />

        <div className="form-grid review-grid">
          <label className="field-wide">
            Название задачи
            <input
              value={taskName}
              maxLength={TASK_NAME_MAX_LENGTH}
              disabled={!editable}
              placeholder="Коротко, в форме действия"
              onChange={(event) => setTaskName(event.target.value)}
            />
          </label>

          <label>
            Подразделение
            <select
              value={departmentId ?? ""}
              disabled={!editable}
              onChange={(event) =>
                setDepartmentId(
                  event.target.value ? Number(event.target.value) : null,
                )
              }
            >
              <option value="">Не указано</option>
              {departments.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            Приоритет
            <select
              value={priority}
              disabled={!editable}
              onChange={(event) => setPriority(Number(event.target.value) as Priority)}
            >
              {PRIORITIES.map((value) => (
                <option key={value} value={value}>
                  P{value} · {PRIORITY_LABEL[value]}
                </option>
              ))}
            </select>
          </label>

          <label className="field-wide">
            Описание
            <textarea
              value={taskDescription}
              maxLength={TASK_DESCRIPTION_MAX_LENGTH}
              disabled={!editable}
              placeholder="Что нужно сделать, контекст, сроки и ответственные"
              onChange={(event) => setTaskDescription(event.target.value)}
            />
            <span
              className={[
                "field-counter",
                taskDescription.length > TASK_DESCRIPTION_MAX_LENGTH * 0.9 ? "is-visible" : "",
                taskDescription.length >= TASK_DESCRIPTION_MAX_LENGTH ? "is-limit" : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {taskDescription.length}/{TASK_DESCRIPTION_MAX_LENGTH}
            </span>
          </label>
        </div>

        {rejecting && (
          <div className="reject-box">
            <label className="field-wide">
              Причина отклонения
              <textarea
                value={rejectReason}
                maxLength={REJECTION_REASON_MAX_LENGTH}
                autoFocus
                placeholder="Например: ошиблись номером, задача не нужна"
                onChange={(event) => setRejectReason(event.target.value)}
              />
            </label>
            <div className="reject-actions">
              <button
                className="secondary"
                type="button"
                disabled={busy}
                onClick={() => {
                  setRejecting(false);
                  setRejectReason("");
                }}
              >
                Назад
              </button>
              <button
                className="danger"
                type="button"
                disabled={busy}
                onClick={() => onReject(rejectReason)}
              >
                <Ban size={16} />
                Подтвердить отклонение
              </button>
            </div>
          </div>
        )}

        {editable && !rejecting && (
          <div className="edit-actions">
            <button
              className="secondary"
              type="button"
              disabled={busy}
              onClick={() => setRejecting(true)}
            >
              <Ban size={16} />
              Отклонить
            </button>
            <button type="submit" disabled={!canSubmit}>
              {candidate.status === "failed" ? <RefreshCw size={16} /> : <Send size={16} />}
              {busy
                ? "Отправляю…"
                : candidate.status === "failed"
                  ? "Повторить создание"
                  : "Создать задачу"}
            </button>
          </div>
        )}

        {!editable && !rejecting && (
          <div className="edit-actions">
            <button type="button" onClick={onClose}>
              Закрыть
            </button>
          </div>
        )}

        <div className="record-delete-row">
          <button
            className="secondary danger-text"
            type="button"
            disabled={busy}
            onClick={onDelete}
          >
            <Trash2 size={16} />
            Удалить запись из приложения
          </button>
        </div>
      </form>
    </div>
  );
}
