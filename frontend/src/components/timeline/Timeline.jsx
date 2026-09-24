import { AlertTriangle, Check, Circle, Info, Loader2, Sparkles, X } from 'lucide-react';
import { formatShortDate, formatTime } from '../../utils/date';

const LEVEL_ICON = { success: Check, info: Info, warning: AlertTriangle, error: X };

/** Vertical event timeline (meeting flags or lead journey). */
export function Timeline({ events, empty = 'No events yet', showDate = true }) {
  if (!events?.length) return <p className="muted">{empty}</p>;
  return (
    <ol className="timeline">
      {events.map((e, i) => {
        const level = e.level || 'success';
        const Icon = LEVEL_ICON[level] || Circle;
        return (
          <li key={`${e.key || e.event}-${i}`} className={`timeline-item tl-${level}`}>
            <div className="timeline-time tabular">
              {showDate && <span>{formatShortDate(e.at)}</span>}
              <span>{formatTime(e.at)}</span>
            </div>
            <div className="timeline-marker" aria-hidden="true">
              <Icon size={11} strokeWidth={3} />
            </div>
            <div className="timeline-content">
              <div className="row wrap" style={{ gap: 6 }}>
                <span className="timeline-label">{e.label}</span>
                {e.ai_generated && (
                  <span className="badge badge-ai badge-sm"><Sparkles size={10} /> AI</span>
                )}
                {e.source && <span className="timeline-source">{e.source}</span>}
              </div>
              {e.details && <div className="timeline-details">{e.details}</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

const STEP_ICON = { done: Check, error: X, warning: AlertTriangle, active: Loader2, skipped: Check };

/** The sales-person-facing lifecycle: Scheduled ✓ → Lead Invited ✓ → Waiting… → … */
export function JourneyStepper({ steps, compact = false }) {
  if (!steps?.length) return null;
  return (
    <ol className={`journey ${compact ? 'journey-compact' : ''}`} aria-label="Meeting progress">
      {steps.map((s) => {
        const Icon = STEP_ICON[s.state] || Circle;
        return (
          <li key={s.key} className={`journey-step js-${s.state}`}>
            <span className="journey-dot" aria-hidden="true">
              <Icon size={12} strokeWidth={3} className={s.state === 'active' ? 'spin' : ''} />
            </span>
            <span className="journey-text">
              <span className="journey-label">{s.label}</span>
              {s.at && <span className="journey-at tabular">{formatTime(s.at)}</span>}
              {s.note && <span className="journey-note">{s.note}</span>}
            </span>
            <span className="sr-only">({s.state})</span>
          </li>
        );
      })}
    </ol>
  );
}
