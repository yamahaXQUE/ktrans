import { ChevronRight } from "lucide-react";
import type { KeyboardEvent } from "react";
import type { OperatorSummary } from "../../types/domain";
import { formatDateTime } from "../../utils/date";

type OperatorListProps = {
  operators: OperatorSummary[];
  onSelect: (operator: OperatorSummary) => void;
};

function handleKeyDown(
  event: KeyboardEvent<HTMLElement>,
  operator: OperatorSummary,
  onSelect: (operator: OperatorSummary) => void,
) {
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }
  event.preventDefault();
  onSelect(operator);
}

export function OperatorList({ operators, onSelect }: OperatorListProps) {
  return (
    <div className="operator-list">
      {operators.map((operator) => (
        <article
          key={operator.id}
          className="operator-card is-openable"
          role="button"
          tabIndex={0}
          aria-label={`Открыть оператора ${operator.displayName}`}
          onClick={() => onSelect(operator)}
          onKeyDown={(event) => handleKeyDown(event, operator, onSelect)}
        >
          <div className="operator-identity">
            <span className="operator-avatar">{operator.initials || "?"}</span>
            <div className="operator-name">
              <strong>{operator.displayName}</strong>
              <span>{operator.workPosition || "Оператор"}</span>
            </div>
          </div>

          <div className="operator-stats">
            <span className="stat-box">
              <strong>{operator.callCount}</strong>
              <span>звонки</span>
            </span>
            <span className="stat-box stat-pending">
              <strong>{operator.pendingCount}</strong>
              <span>ждут</span>
            </span>
            <span className="stat-box stat-failed">
              <strong>{operator.failedCount}</strong>
              <span>упало</span>
            </span>
            <span className="stat-box stat-confirmed">
              <strong>{operator.confirmedCount}</strong>
              <span>создано</span>
            </span>
          </div>

          <div className="operator-foot">
            <span>
              {operator.lastCallAt
                ? `Последний звонок: ${formatDateTime(operator.lastCallAt)}`
                : "Звонков пока нет"}
            </span>
            <ChevronRight size={18} />
          </div>
        </article>
      ))}
    </div>
  );
}
