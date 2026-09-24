import { Sparkles, FlaskConical } from 'lucide-react';
import { meetingState, LEVELS, LEAD_STATUSES, STAGE_STATUS, NOTIFICATION_STATUS, FLAG_LABELS, flagTone } from '../../utils/status';

const toneClass = (tone) => (tone && tone !== 'neutral' ? `badge-${tone}` : '');

export function Badge({ tone = 'neutral', dot = false, pulse = false, size, children, title, icon: Icon }) {
  return (
    <span className={`badge ${toneClass(tone)} ${pulse ? 'pulse' : ''} ${size === 'sm' ? 'badge-sm' : ''}`} title={title}>
      {dot && <span className="dot" aria-hidden="true" />}
      {Icon && <Icon aria-hidden="true" />}
      {children}
    </span>
  );
}

export function StatusBadge({ state, label }) {
  const s = meetingState(state);
  return (
    <Badge tone={s.tone} dot pulse={s.pulse}>
      {label || s.label}
    </Badge>
  );
}

export function LevelBadge({ level, prefix, ai = true }) {
  if (!level) return <span className="muted">—</span>;
  const l = LEVELS[level] || LEVELS.unknown;
  return (
    <Badge tone={l.tone} title={ai ? 'AI generated' : undefined}>
      {prefix ? `${prefix}: ` : ''}
      {l.label}
    </Badge>
  );
}

export function LeadStatusBadge({ status }) {
  const s = LEAD_STATUSES[status] || { label: status || '—', tone: 'neutral' };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export function StageBadge({ status }) {
  const s = STAGE_STATUS[status] || { label: status || '—', tone: 'neutral' };
  return (
    <Badge tone={s.tone} dot pulse={s.pulse}>
      {s.label}
    </Badge>
  );
}

export function NotificationBadge({ status }) {
  const s = NOTIFICATION_STATUS[status] || { label: status || '—', tone: 'neutral' };
  return (
    <Badge tone={s.tone} dot>
      {s.label}
    </Badge>
  );
}

export function AIBadge({ label = 'AI generated', size = 'sm' }) {
  return (
    <Badge tone="ai" size={size} icon={Sparkles} title="Produced by AI analysis — interpretation, not verified fact">
      {label}
    </Badge>
  );
}

export function DemoBadge() {
  return (
    <Badge tone="neutral" size="sm" icon={FlaskConical} title="Seed / demo data">
      Demo
    </Badge>
  );
}

export function FlagChip({ flag, ai }) {
  return (
    <span className={`flag-chip flag-${flagTone(flag)}`} title={ai ? 'AI-derived flag' : undefined}>
      {FLAG_LABELS[flag] || flag}
      {ai && <Sparkles size={11} aria-label="AI generated" />}
    </span>
  );
}
