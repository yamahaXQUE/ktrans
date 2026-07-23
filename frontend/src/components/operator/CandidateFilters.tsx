import type { CandidateStatus, Department } from "../../types/domain";
import { STATUS_LABEL } from "../../constants/task";

export type StatusFilter = "all" | CandidateStatus;

const STATUS_ORDER: CandidateStatus[] = ["pending", "failed", "confirmed", "rejected"];

type CandidateFiltersProps = {
  departments: Department[];
  status: StatusFilter;
  department: string | "all";
  onStatusChange: (status: StatusFilter) => void;
  onDepartmentChange: (department: string | "all") => void;
  onHide: () => void;
};

export function CandidateFilters({
  departments,
  status,
  department,
  onStatusChange,
  onDepartmentChange,
  onHide,
}: CandidateFiltersProps) {
  return (
    <section className="filter-panel" aria-label="Фильтры кандидатов">
      <div className="filter-row">
        <span className="filter-title">Статус</span>
        <div className="chip-strip">
          <button
            className={status === "all" ? "chip is-active" : "chip"}
            type="button"
            onClick={() => onStatusChange("all")}
          >
            Все
          </button>
          {STATUS_ORDER.map((item) => (
            <button
              className={item === status ? "chip is-active" : "chip"}
              key={item}
              type="button"
              onClick={() => onStatusChange(item)}
            >
              {STATUS_LABEL[item]}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-row">
        <span className="filter-title">Отдел</span>
        <div className="chip-strip">
          <button
            className={department === "all" ? "chip is-active" : "chip"}
            type="button"
            onClick={() => onDepartmentChange("all")}
          >
            Все
          </button>
          {departments.map((item) => (
            <button
              className={item.name === department ? "chip is-active" : "chip"}
              key={item.id}
              type="button"
              onClick={() => onDepartmentChange(item.name)}
            >
              {item.name}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-actions">
        <button className="secondary" type="button" onClick={onHide}>
          Скрыть
        </button>
      </div>
    </section>
  );
}
