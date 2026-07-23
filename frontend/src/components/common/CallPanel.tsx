import { ArrowDownLeft, ArrowUpRight, Clock, Phone, PhoneOff } from "lucide-react";
import type { SourceCall } from "../../types/domain";
import { directionLabel, formatDuration } from "../../utils/format";
import { formatDateTime } from "../../utils/date";

type CallPanelProps = {
  call: SourceCall;
  /** When false the transcript block is hidden (compact meta only). */
  showTranscript?: boolean;
};

/**
 * Read-only view of a source call: masked meta + Whisper transcript.
 * Raw phone numbers and recording URLs never reach the frontend, so this
 * shows only the masked number the backend allows.
 */
export function CallPanel({ call, showTranscript = true }: CallPanelProps) {
  const DirectionIcon = call.direction === "inbound" ? ArrowDownLeft : ArrowUpRight;

  return (
    <section className="call-panel" aria-label="Исходный звонок">
      <div className="call-meta-grid">
        <div className="call-meta-item">
          <DirectionIcon size={18} />
          <div>
            <span>Тип</span>
            <strong>{directionLabel(call.direction)}</strong>
          </div>
        </div>
        <div className="call-meta-item">
          <Clock size={18} />
          <div>
            <span>Длительность</span>
            <strong>{formatDuration(call.durationSeconds)}</strong>
          </div>
        </div>
        <div className="call-meta-item">
          <Phone size={18} />
          <div>
            <span>Номер</span>
            <strong>{call.phoneMasked}</strong>
          </div>
        </div>
        <div className="call-meta-item">
          <Clock size={18} />
          <div>
            <span>Начало</span>
            <strong>{formatDateTime(call.startedAt)}</strong>
          </div>
        </div>
      </div>

      {call.failedCode && (
        <div className="call-failed">
          <PhoneOff size={15} />
          Звонок с кодом завершения {call.failedCode}
        </div>
      )}

      {showTranscript && (
        <div className="call-transcript-block">
          <span className="field-label">Расшифровка звонка</span>
          <div className="call-transcript">{call.transcript || "Расшифровка недоступна."}</div>
        </div>
      )}
    </section>
  );
}
