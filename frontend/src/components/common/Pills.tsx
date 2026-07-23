import type { CandidateStatus, Priority } from "../../types/domain";
import { PRIORITY_LABEL, PRIORITY_TONE, STATUS_LABEL, STATUS_TONE } from "../../constants/task";

export function PriorityPill({ priority }: { priority: Priority }) {
  return (
    <span className={`priority priority-${PRIORITY_TONE[priority]}`} title="Приоритет">
      P{priority} · {PRIORITY_LABEL[priority]}
    </span>
  );
}

export function StatusPill({ status }: { status: CandidateStatus }) {
  return <span className={`status ${STATUS_TONE[status]}`}>{STATUS_LABEL[status]}</span>;
}
