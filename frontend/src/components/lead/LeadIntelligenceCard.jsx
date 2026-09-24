import { Sparkles } from 'lucide-react';
import { Card } from '../cards/Card';
import { AIBadge, LevelBadge } from '../badges/Badge';
import { NotAvailable } from '../common/States';
import { formatDate } from '../../utils/date';
import { formatDuration } from '../../utils/formatting';

export function LeadIntelligenceCard({ intel }) {
  const i = intel || {};
  const ai = <Sparkles size={11} color="var(--ai)" aria-label="AI generated" />;
  return (
    <Card title="Lead Intelligence" subtitle="Rolled up from stored meeting data only" badge={<AIBadge label="Partly AI" />}>
      <dl className="kv" style={{ gridTemplateColumns: '120px minmax(0,1fr)' }}>
        <dt className="row" style={{ gap: 4 }}>Interest {ai}</dt>
        <dd>{i.interest_level ? <LevelBadge level={i.interest_level} /> : <NotAvailable>No analysed meeting yet</NotAvailable>}</dd>
        <dt className="row" style={{ gap: 4 }}>Intent {ai}</dt>
        <dd>{i.purchase_intent ? <LevelBadge level={i.purchase_intent} /> : <NotAvailable>No analysed meeting yet</NotAvailable>}</dd>
        <dt>Last Meeting</dt>
        <dd>{i.last_meeting_at ? formatDate(i.last_meeting_at) : <NotAvailable>No meetings</NotAvailable>}</dd>
        <dt>Meetings</dt>
        <dd className="tabular">{i.meetings_count ?? 0}</dd>
        <dt>Last Duration</dt>
        <dd>{i.last_duration_seconds ? formatDuration(i.last_duration_seconds) : <NotAvailable />}</dd>
        <dt className="row" style={{ gap: 4 }}>Main Concern {ai}</dt>
        <dd>{i.main_concern || <NotAvailable>None identified</NotAvailable>}</dd>
        <dt className="row" style={{ gap: 4 }}>Next Action {ai}</dt>
        <dd>{i.next_action || <NotAvailable>—</NotAvailable>}</dd>
        <dt>Follow-up</dt>
        <dd>{i.follow_up_required ? <span className="badge badge-warning">Due {formatDate(i.follow_up_due)}</span> : <span className="muted">None open</span>}</dd>
      </dl>
    </Card>
  );
}
