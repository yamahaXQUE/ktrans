import {
  AlertTriangle,
  BarChart3,
  Clock3,
  Download,
  FileSearch,
  MessageSquareWarning,
  PhoneCall,
  Send,
  Split,
} from "lucide-react";
import type { ReactNode } from "react";
import { TASK_TYPE_LABEL } from "../../constants/task";
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
  if (!analytics) {
    return <EmptyState message="аналитика пока недоступна" />;
  }

  const departments = analytics.departments;
  const maxDepartmentCount = Math.max(
    1,
    ...departments.map((item) => item.count),
  );
  const totalErrors =
    analytics.analysisFailedCalls + analytics.deliveryFailedTasks;
  const recentDays = analytics.daily.slice(-14).reverse();
  const funnel = [
    { label: "Звонки загружены", value: analytics.totalCalls },
    { label: "Расшифрованы", value: analytics.analyzedCalls },
    { label: "Найдены жалобы", value: analytics.complaintCandidates },
    { label: "Подтверждены оператором", value: analytics.confirmedCandidates },
    { label: "Созданы в Bitrix", value: analytics.totalComplaints },
  ];

  return (
    <div className="analytics-page">
      <section className="control-panel analytics-toolbar">
        <div>
          <h2>Аналитика обработки звонков</h2>
          <p>
            Воронка расшифровки и доставки жалоб
            <span className="analytics-period">
              {formatPeriod(analytics.periodStart, analytics.periodEnd)}
            </span>
          </p>
        </div>
        <button type="button" disabled={exporting} onClick={onExport}>
          <Download size={17} />
          {exporting ? "Готовлю файл…" : "Выгрузить в Excel"}
        </button>
      </section>

      <section className="analytics-kpis" aria-label="Основные показатели">
        <Kpi
          icon={<PhoneCall />}
          value={analytics.totalCalls}
          label="звонков в базе"
          note="весь доступный период"
        />
        <Kpi
          icon={<FileSearch />}
          value={analytics.analyzedCalls}
          label="расшифровано"
          note={`${formatPercent(analytics.analysisCoveragePercent)} покрытия`}
        />
        <Kpi
          icon={<MessageSquareWarning />}
          value={analytics.complaintCandidates}
          label="найдено жалоб"
          note={`${analytics.rejectedCandidates} отклонено`}
        />
        <Kpi
          icon={<Send />}
          value={analytics.totalComplaints}
          label="создано в Bitrix"
          note={`${formatPercent(analytics.deliverySuccessPercent)} успешных доставок`}
        />
        <Kpi
          icon={<AlertTriangle />}
          value={totalErrors}
          label="ошибок"
          note={`${analytics.analysisFailedCalls} анализ · ${analytics.deliveryFailedTasks} Bitrix`}
          warning={totalErrors > 0}
        />
        <Kpi
          icon={<Clock3 />}
          value={analytics.manualQueueCalls}
          label="в ручной очереди"
          note={`${analytics.analysisPendingCalls} всего без результата`}
          warning={analytics.manualQueueCalls > 0}
        />
      </section>

      <section className="analytics-grid">
        <article className="analytics-card">
          <div className="analytics-card-head">
            <div>
              <h3>Воронка обработки</h3>
              <p>Где теряются звонки от загрузки до задачи в CRM</p>
            </div>
            <Split size={22} />
          </div>
          <div className="analytics-funnel">
            {funnel.map((item, index) => {
              const previous = index === 0 ? item.value : funnel[index - 1].value;
              const conversion = previous ? (item.value * 100) / previous : 0;
              return (
                <div className="analytics-funnel-row" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value.toLocaleString("ru-RU")}</strong>
                  <small>
                    {index === 0 ? "100%" : `${formatPercent(conversion)} от предыдущего этапа`}
                  </small>
                </div>
              );
            })}
          </div>
        </article>

        <article className="analytics-card">
          <div className="analytics-card-head">
            <div>
              <h3>Типы найденных задач</h3>
              <p>Распределение всех кандидатов с жалобой</p>
            </div>
          </div>
          {analytics.taskTypes.length ? (
            <div className="analytics-table-wrap">
              <table className="analytics-table">
                <thead>
                  <tr>
                    <th>Тип</th>
                    <th>Найдено</th>
                    <th>Доля</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.taskTypes.map((item) => (
                    <tr key={item.taskType}>
                      <td>{TASK_TYPE_LABEL[item.taskType]}</td>
                      <td>{item.count}</td>
                      <td>{formatPercent(item.sharePercent)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="analytics-empty-note">Жалобы пока не найдены.</p>
          )}
        </article>
      </section>

      <section className="analytics-grid">
        <article className="analytics-card">
          <div className="analytics-card-head">
            <div>
              <h3>Созданные жалобы по отделам</h3>
              <p>Только задачи, которые Bitrix успешно принял</p>
            </div>
            <BarChart3 size={22} />
          </div>
          {departments.length ? (
            <div className="department-bars">
              {departments.map((item) => (
                <div className="department-bar-row" key={item.department}>
                  <div className="department-bar-label">
                    <span>{item.department}</span>
                    <strong>
                      {item.count} · {formatPercent(item.sharePercent)}
                    </strong>
                  </div>
                  <div className="department-bar-track" aria-hidden="true">
                    <span
                      style={{
                        width: `${Math.max(4, (item.count / maxDepartmentCount) * 100)}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="analytics-empty-note">
              Успешно созданных задач пока нет. Кандидаты и ошибки видны выше.
            </p>
          )}
        </article>

        <article className="analytics-card">
          <div className="analytics-card-head">
            <div>
              <h3>Состояние очереди</h3>
              <p>Что требует внимания прямо сейчас</p>
            </div>
          </div>
          <div className="analytics-status-list">
            <StatusRow label="Ожидают или обрабатываются" value={analytics.analysisPendingCalls} />
            <StatusRow label="Запрошены вручную" value={analytics.manualQueueCalls} />
            <StatusRow label="Ошибки анализа" value={analytics.analysisFailedCalls} warning />
            <StatusRow
              label="Ошибки отправки в Bitrix"
              value={analytics.deliveryFailedTasks}
              warning
            />
          </div>
        </article>
      </section>

      <section className="analytics-card">
        <div className="analytics-card-head">
          <div>
            <h3>Динамика по дням</h3>
            <p>Последние {recentDays.length} дней с данными, новые сверху</p>
          </div>
        </div>
        {recentDays.length ? (
          <div className="analytics-table-wrap">
            <table className="analytics-table analytics-table-daily">
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Звонки</th>
                  <th>Расшифровано</th>
                  <th>Ошибки</th>
                  <th>Жалобы</th>
                  <th>Создано в Bitrix</th>
                </tr>
              </thead>
              <tbody>
                {recentDays.map((item) => (
                  <tr key={item.day}>
                    <td>{formatDay(item.day)}</td>
                    <td>{item.calls}</td>
                    <td>{item.analyzedCalls}</td>
                    <td>{item.analysisFailures}</td>
                    <td>{item.complaintCandidates}</td>
                    <td>{item.createdTasks}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="analytics-empty-note">Данных по дням пока нет.</p>
        )}
      </section>
    </div>
  );
}

function Kpi({
  icon,
  value,
  label,
  note,
  warning = false,
}: {
  icon: ReactNode;
  value: number;
  label: string;
  note: string;
  warning?: boolean;
}) {
  return (
    <article className={`analytics-kpi${warning ? " is-warning" : ""}`}>
      {icon}
      <div>
        <strong>{value.toLocaleString("ru-RU")}</strong>
        <span>{label}</span>
        <small>{note}</small>
      </div>
    </article>
  );
}

function StatusRow({
  label,
  value,
  warning = false,
}: {
  label: string;
  value: number;
  warning?: boolean;
}) {
  return (
    <div className={`analytics-status-row${warning && value ? " is-warning" : ""}`}>
      <span>{label}</span>
      <strong>{value.toLocaleString("ru-RU")}</strong>
    </div>
  );
}

function formatPercent(value: number): string {
  return `${value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%`;
}

function formatPeriod(start: string | null, end: string | null): string {
  if (!start || !end) {
    return "данных пока нет";
  }
  const firstDay = new Date(start).toLocaleDateString("ru-RU");
  const lastDay = new Date(end).toLocaleDateString("ru-RU");
  return `${firstDay} — ${lastDay}`;
}

function formatDay(day: string): string {
  return new Date(`${day}T00:00:00`).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}
