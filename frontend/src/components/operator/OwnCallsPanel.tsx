import {
  ArrowDownLeft,
  ArrowUpRight,
  AudioLines,
  FileText,
  LoaderCircle,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react";
import type { SourceCall, TaskCandidate } from "../../types/domain";
import { formatDateTime } from "../../utils/date";
import { directionLabel, formatDuration } from "../../utils/format";
import { EmptyState } from "../common/EmptyState";
import { LoadingState } from "../common/LoadingState";
import { StatusPill } from "../common/Pills";

type OwnCallsPanelProps = {
  calls: SourceCall[];
  candidateByCallId: Map<string, TaskCandidate>;
  loading: boolean;
  requestingCallId: string | null;
  onOpenCall: (call: SourceCall) => void;
  onOpenCandidate: (candidate: TaskCandidate) => void;
  onRequestAnalysis: (call: SourceCall) => void;
  onDelete: (call: SourceCall) => void;
};

export function OwnCallsPanel({
  calls,
  candidateByCallId,
  loading,
  requestingCallId,
  onOpenCall,
  onOpenCandidate,
  onRequestAnalysis,
  onDelete,
}: OwnCallsPanelProps) {
  if (loading) {
    return <LoadingState />;
  }
  if (calls.length === 0) {
    return <EmptyState message="у вас пока нет синхронизированных звонков" />;
  }

  return (
    <section className="archive-panel">
      <div className="view-header">
        <div>
          <h2>Мои звонки</h2>
          <p>Все звонки из Bitrix · записей: {calls.length}</p>
        </div>
      </div>

      <div className="archive-list">
        {calls.map((call) => {
          const candidate = candidateByCallId.get(call.id);
          const DirectionIcon =
            call.direction === "inbound" ? ArrowDownLeft : ArrowUpRight;
          const requesting = requestingCallId === call.id;
          const processing = call.analysisStatus === "processing";
          const queued =
            call.analysisStatus === "pending" && call.analysisRequested;
          const failed = call.analysisStatus === "failed";

          return (
            <article
              key={call.id}
              className="call-row is-openable"
              role="button"
              tabIndex={0}
              onClick={() =>
                candidate ? onOpenCandidate(candidate) : onOpenCall(call)
              }
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  candidate ? onOpenCandidate(candidate) : onOpenCall(call);
                }
              }}
            >
              <div className="call-row-main">
                <span className="call-row-direction">
                  <DirectionIcon size={16} />
                  {directionLabel(call.direction)}
                </span>
                <strong className="call-row-title">
                  {candidate?.conversationTitle ||
                    call.conversationTitle ||
                    `Звонок ${call.statisticId}`}
                </strong>
                <span className="call-row-meta">
                  {formatDateTime(call.startedAt)} ·{" "}
                  {formatDuration(call.durationSeconds)} · {call.phoneMasked}
                </span>
                {failed && (
                  <span className="call-row-error">
                    Расшифровка не выполнена. Можно повторить запрос.
                  </span>
                )}
              </div>

              <div className="call-row-side">
                {candidate ? (
                  <>
                    <StatusPill status={candidate.status} />
                    <button
                      className="secondary call-row-analysis"
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onOpenCandidate(candidate);
                      }}
                    >
                      {candidate.status === "pending" ? (
                        <Sparkles size={15} />
                      ) : (
                        <FileText size={15} />
                      )}
                      {candidate.status === "pending"
                        ? "Решить по задаче"
                        : "Открыть"}
                    </button>
                  </>
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
                    ) : failed ? (
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
                          : failed
                            ? "Повторить"
                            : "Расшифровать"}
                  </button>
                )}

                <button
                  className="secondary danger-text icon-button"
                  type="button"
                  title="Удалить запись"
                  aria-label="Удалить запись"
                  onClick={(event) => {
                    event.stopPropagation();
                    onDelete(call);
                  }}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
