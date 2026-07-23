import {
  BarChart3,
  Building2,
  Download,
  MessageSquareWarning,
  Trophy,
} from "lucide-react";
import type { ComplaintAnalytics } from "../../types/domain";
import { EmptyState } from "../common/EmptyState";
import { LoadingState } from "../common/LoadingState";

type AnalyticsDashboardProps = {
  analytics: ComplaintAnalytics | null;
  loading: boolean;
  exporting: boolean;
  onExport: () => void;
};

export function AnalyticsDashboard({
  analytics,
  loading,
  exporting,
  onExport,
}: AnalyticsDashboardProps) {
  if (loading) {
    return <LoadingState />;
  }

  const departments = analytics?.departments ?? [];
  const total = analytics?.totalComplaints ?? 0;
  const leader = departments[0] ?? null;
  const maxCount = Math.max(1, ...departments.map((item) => item.count));

  return (
    <div className="analytics-page">
      <section className="control-panel analytics-toolbar">
        <div>
          <h2>Аналитика жалоб</h2>
          <p>
            Считаем только созданные в Bitrix задачи и группируем их по
            выбранному тегу отдела.
          </p>
        </div>
        <button type="button" disabled={exporting} onClick={onExport}>
          <Download size={17} />
          {exporting ? "Готовлю файл…" : "Выгрузить в Excel"}
        </button>
      </section>

      <section className="analytics-kpis" aria-label="Основные показатели">
        <article className="analytics-kpi">
          <MessageSquareWarning size={22} />
          <div>
            <strong>{total}</strong>
            <span>отправленных жалоб</span>
          </div>
        </article>
        <article className="analytics-kpi">
          <Building2 size={22} />
          <div>
            <strong>{departments.length}</strong>
            <span>отделов в задачах</span>
          </div>
        </article>
        <article className="analytics-kpi analytics-kpi-wide">
          <Trophy size={22} />
          <div>
            <strong>{leader?.department ?? "Пока нет данных"}</strong>
            <span>
              {leader
                ? `${leader.count} жалоб · ${leader.sharePercent.toLocaleString("ru-RU")}%`
                : "лидирующий отдел появится после первой задачи"}
            </span>
          </div>
        </article>
      </section>

      {departments.length === 0 ? (
        <EmptyState message="отправленных жалоб пока нет" />
      ) : (
        <section className="analytics-grid">
          <article className="analytics-card">
            <div className="analytics-card-head">
              <div>
                <h3>Жалобы по отделам</h3>
                <p>Количество выбранных тегов в созданных задачах</p>
              </div>
              <BarChart3 size={22} />
            </div>
            <div className="department-bars">
              {departments.map((item) => (
                <div className="department-bar-row" key={item.department}>
                  <div className="department-bar-label">
                    <span>{item.department}</span>
                    <strong>{item.count}</strong>
                  </div>
                  <div className="department-bar-track" aria-hidden="true">
                    <span
                      style={{
                        width: `${Math.max(4, (item.count / maxCount) * 100)}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </article>

          <article className="analytics-card">
            <div className="analytics-card-head">
              <div>
                <h3>Распределение</h3>
                <p>Доля каждого отдела от всех отправленных жалоб</p>
              </div>
            </div>
            <div className="analytics-table-wrap">
              <table className="analytics-table">
                <thead>
                  <tr>
                    <th>Отдел</th>
                    <th>Жалобы</th>
                    <th>Доля</th>
                  </tr>
                </thead>
                <tbody>
                  {departments.map((item) => (
                    <tr key={item.department}>
                      <td>{item.department}</td>
                      <td>{item.count}</td>
                      <td>{item.sharePercent.toLocaleString("ru-RU")}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </section>
      )}
    </div>
  );
}
