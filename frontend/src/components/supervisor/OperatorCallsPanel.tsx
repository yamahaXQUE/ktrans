import {
  ArrowDownLeft,
  ArrowLeft,
  ArrowUpRight,
  AudioLines,
  FileText,
  LoaderCircle,
  RefreshCw,
} from "lucide-react";
import type { OperatorSummary, SourceCall, TaskCandidate } from "../../types/domain";
import { directionLabel, formatDuration } from "../../utils/format";
import { formatDateTime } from "../../utils/date";
import { StatusPill } from "../common/Pills";
import { EmptyState } from "../common/EmptyState";
import { LoadingState } from "../common/LoadingState";

type OperatorCallsPanelProps = {
  operator: OperatorSummary;
  calls: SourceCall[];
  candidateByCallId: Map<string, TaskCandidate>;
  loading: boolean;
  requestingCallId: string | null;
  onBack: () => void;
  onOpenCall: (call: SourceCall) => void;
  onRequestAnalysis: (call: SourceCall) => void;
};

export function OperatorCallsPanel({
  operator,
  calls,
  candidateByCallId,
  loading,
  requestingCallId,
  onBack,
  onOpenCall,
  onRequestAnalysis,
}: OperatorCallsPanelProps) {
  return (
    <section className="archive-panel">
      <div className="view-header">
        <div className="operator-detail-head">
          <button className="secondary icon-button" type="button" title="Назад" onClick={onBack}>
            <ArrowLeft size={17} />
          </button>
          <div>
            <h2>{operator.displayName}</h2>
            <p>
              {operator.workPosition || "Оператор"} · звонков: {operator.callCount}
            </p>
          </div>
        </div>
      </div>

      {loading ? (
        <LoadingState />
      ) : calls.length === 0 ? (
        <EmptyState message="у этого оператора пока нет звонков" />
      ) : (
        <div className="archive-list">
          {calls.map((call) => {
            const candidate = candidateByCallId.get(call.id);
            const DirectionIcon = call.direction === "inbound" ? ArrowDownLeft : ArrowUpRight;
            const requesting = requestingCallId === call.id;
            const processing = call.analysisStatus === "processing";
            const queued =
              call.analysisStatus === "pending" && call.analysisRequested;
            const retrying = call.analysisStatus === "failed";
            return (
              <article
                key={call.id}
                className="call-row is-openable"
                role="button"
                tabIndex={0}
                aria-label={`Открыть расшифровку звонка ${call.id}`}
                onClick={() => onOpenCall(call)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onOpenCall(call);
                  }
                }}
              >
                <div className="call-row-main">
                  <span className="call-row-direction">
                    <DirectionIcon size={16} />
                    {directionLabel(call.direction)}
                  </span>
                  <strong className="call-row-title">
                    {candidate && candidate.taskName.trim()
                      ? candidate.taskName
                      : `Звонок ${call.id}`}
                  </strong>
                  <span className="call-row-meta">
                    {formatDateTime(call.startedAt)} · {formatDuration(call.durationSeconds)} ·{" "}
                    {call.phoneMasked}
                  </span>
                </div>
                <div className="call-row-side">
                  {candidate ? (
                    <StatusPill status={candidate.status} />
                  ) : (
                    <span className="status archive">Нет кандидата</span>
                  )}
                  {candidate ? (
                    <span className="call-row-open">
                      <FileText size={16} />
                      Расшифровка
                    </span>
                  ) : (
                    <button
                      className="secondary call-row-analysis"
                      type="button"
                      disabled={requesting || processing || queued}
                      onClick={(event) => {
                        event.stopPropagation();
                        onRequestAnalysis(call);
                      }}
                    >
                      {requesting || processing ? (
                        <LoaderCircle className="is-spinning" size={15} />
                      ) : retrying ? (
                        <RefreshCw size={15} />
                      ) : (
                        <AudioLines size={15} />
                      )}
                      {requesting
                        ? "Ставлю в очередь…"
                        : processing
                          ? "Обрабатывается"
                          : queued
                            ? "В очереди"
                            : retrying
                              ? "Повторить анализ"
                              : "Расшифровать"}
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
