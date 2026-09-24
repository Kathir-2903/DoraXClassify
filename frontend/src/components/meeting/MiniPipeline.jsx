import { Check, Loader2, Minus, X, Clock, AlertTriangle } from 'lucide-react';

const ICON = { completed: Check, processing: Loader2, failed: X, skipped: Minus, unavailable: AlertTriangle, pending: Clock };
const COLOR = { completed: 'var(--success)', processing: 'var(--accent)', failed: 'var(--error)', unavailable: 'var(--warning)', skipped: 'var(--text-3)', pending: 'var(--text-3)' };

/** Compact Recording → Transcript → AI indicator for tables. */
export function MiniPipeline({ processing, completed }) {
  if (!completed) return <span className="muted">—</span>;
  const stages = [['recording', 'Rec'], ['transcript', 'Txt'], ['analysis', 'AI']];
  return (
    <span className="row" style={{ gap: 6 }} aria-label="Processing status">
      {stages.map(([k, label]) => {
        const s = processing?.[k]?.status || 'pending';
        const Icon = ICON[s] || Clock;
        return (
          <span key={k} className="row" style={{ gap: 2, fontSize: 11, color: COLOR[s] }} title={`${k}: ${s}`}>
            <Icon size={12} className={s === 'processing' ? 'spin' : ''} aria-hidden="true" />
            {label}
          </span>
        );
      })}
    </span>
  );
}
