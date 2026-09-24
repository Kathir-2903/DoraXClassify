import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Building2, CalendarCheck2, CalendarPlus, CheckCircle2, Clock3, ListChecks, Mail, Pencil, Phone, Sparkles, UserRound,
} from 'lucide-react';
import { useLead, useLeadAnalytics } from '../../hooks/useLeads';
import { useAuth } from '../../hooks/useAuth';
import { useToast } from '../../hooks/useToast';
import { invalidateCache } from '../../hooks/useAsync';
import { leadApi } from '../../services/leadApi';
import { errorText } from '../../services/api';
import { Card } from '../../components/cards/Card';
import { KpiCard } from '../../components/cards/KpiCard';
import { DemoBadge, LeadStatusBadge, LevelBadge, StatusBadge } from '../../components/badges/Badge';
import { Timeline } from '../../components/timeline/Timeline';
import { EmptyState, ErrorState } from '../../components/common/States';
import { SkeletonCard } from '../../components/common/Skeleton';
import { LeadIntelligenceCard } from '../../components/lead/LeadIntelligenceCard';
import { LeadFormModal } from '../../components/modals/LeadFormModal';
import { ScheduleMeetingModal } from '../../components/modals/ScheduleMeetingModal';
import { formatDuration, initials } from '../../utils/formatting';
import { formatDate, formatDateTime } from '../../utils/date';
import { LEAD_STATUSES, OBJECTION_LABELS } from '../../utils/status';

const SOURCE_LABEL = { user: 'Sales', classify: 'Classify', ai: 'AI', system: 'System' };

export default function LeadDetails() {
  const { leadId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { isAdmin } = useAuth();
  const lead = useLead(leadId);
  const analytics = useLeadAnalytics(leadId);
  const [editing, setEditing] = useState(false);
  const [scheduling, setScheduling] = useState(false);

  if (lead.error) return <div className="page"><ErrorState error={lead.error} onRetry={lead.refetch} title="Lead not available" /></div>;
  const l = lead.data;
  const a = analytics.data;

  const refresh = () => {
    invalidateCache(`lead:${leadId}`);
    invalidateCache(`lead-analytics:${leadId}`);
    lead.refetch({ silent: true });
    analytics.refetch({ silent: true });
  };

  const changeStatus = async (status) => {
    try {
      await leadApi.update(leadId, { lead_status: status });
      invalidateCache('leads');
      toast.success('Lead status updated', LEAD_STATUSES[status]?.label);
      refresh();
    } catch (err) {
      toast.error('Could not update status', errorText(err));
    }
  };

  const journey = (a?.journey || []).map((e) => ({
    key: e.event,
    label: e.label,
    at: e.at,
    level: e.event === 'no_show' ? 'error' : e.event === 'objection' || e.event === 'follow_up_suggested' ? 'warning' : e.source === 'ai' ? 'info' : 'success',
    source: SOURCE_LABEL[e.source] || e.source,
    details: e.details,
    ai_generated: e.source === 'ai',
  }));

  return (
    <div className="page">
      <button className="btn btn-sm btn-ghost" onClick={() => navigate(-1)} style={{ marginBottom: 10 }}><ArrowLeft /> Back</button>
      {!l ? (
        <SkeletonCard lines={2} />
      ) : (
        <div className="card card-body" style={{ marginBottom: 16 }}>
          <div className="row-between wrap">
            <div className="lead-header">
              <span className="avatar avatar-lg">{initials(l.name)}</span>
              <div>
                <div className="row wrap" style={{ gap: 8 }}>
                  <h1 style={{ fontSize: 'var(--fs-xl)' }}>{l.name}</h1>
                  <LeadStatusBadge status={l.lead_status} />
                  {l.is_demo && <DemoBadge />}
                </div>
                <div className="contact" style={{ marginTop: 4 }}>
                  <span><Mail size={13} /> {l.email}</span>
                  <span className="tabular"><Phone size={13} /> {l.phone}</span>
                  {l.company && <span><Building2 size={13} /> {l.company}</span>}
                  <span><UserRound size={13} /> {l.sales_person?.name || 'Unassigned'}</span>
                </div>
                {(l.interested_product || l.lead_source) && (
                  <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
                    {l.interested_product && <span className="tag">🎯 {l.interested_product}</span>}
                    {l.lead_source && <span className="tag">Source: {l.lead_source}</span>}
                  </div>
                )}
              </div>
            </div>
            <div className="page-actions">
              {isAdmin && (
                <select className="select" style={{ width: 170 }} value={l.lead_status} onChange={(e) => changeStatus(e.target.value)} aria-label="Lead status">
                  {Object.entries(LEAD_STATUSES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
              )}
              {isAdmin && <button className="btn" onClick={() => setEditing(true)}><Pencil /> Edit</button>}
              {!isAdmin && <button className="btn btn-primary" onClick={() => setScheduling(true)}><CalendarPlus /> Schedule Video Call</button>}
            </div>
          </div>
          {l.notes && <p className="secondary" style={{ marginTop: 12, fontSize: 13 }}>{l.notes}</p>}
        </div>
      )}

      <div className="kpi-grid" style={{ marginBottom: 16, '--kpi-cols': 6 }}>
        <KpiCard loading={analytics.loading} label="Total Meetings" value={a?.summary.total_meetings} icon={CalendarCheck2} />
        <KpiCard loading={analytics.loading} label="Completed Meetings" value={a?.summary.completed_meetings} hint={a?.summary.no_shows ? `${a.summary.no_shows} no-show` : ''} icon={CheckCircle2} tone="success" />
        <KpiCard loading={analytics.loading} label="Average Duration" value={formatDuration(a?.summary.average_duration_seconds)} hint={a ? `${formatDuration(a.summary.total_conversation_seconds)} total conversation` : ''} icon={Clock3} />
        <KpiCard loading={analytics.loading} label="Last Meeting" value={a?.summary.latest_interaction ? formatDate(a.summary.latest_interaction) : '—'} hint={a?.summary.first_interaction ? `First: ${formatDate(a.summary.first_interaction)}` : ''} icon={CalendarCheck2} />
        <KpiCard loading={analytics.loading} label="Follow-ups" value={a?.summary.open_follow_ups} hint="Open" icon={ListChecks} tone="warning" />
        <KpiCard loading={analytics.loading} label="Interest" value={a?.intelligence?.interest_level ? a.intelligence.interest_level[0].toUpperCase() + a.intelligence.interest_level.slice(1) : '—'} ai={Boolean(a?.intelligence?.interest_level)} icon={Sparkles} tone="ai" />
      </div>

      <div className="split">
        <div className="stack">
          <Card title="Meeting history" subtitle="Each meeting keeps its own analysis — nothing is overwritten">
            {!a ? <SkeletonCard lines={3} /> : !a.history.length ? (
              <EmptyState icon={CalendarPlus} title="No meetings yet" description="Schedule a Classify meeting to start this lead's sales journey."
                          action={!isAdmin && <button className="btn btn-primary btn-sm" onClick={() => setScheduling(true)}><CalendarPlus /> Schedule Video Call</button>} />
            ) : (
              <div>
                {[...a.history].reverse().map((h) => (
                  <Link key={h.meeting_id} to={`/meetings/${h.meeting_id}`} className="meeting-history-item">
                    <span className="seq-pill">{h.label}</span>
                    <div style={{ minWidth: 0 }}>
                      <div className="row wrap" style={{ gap: 8 }}>
                        <span className="cell-primary">{formatDateTime(h.start_time)}</span>
                        <StatusBadge state={h.status} />
                      </div>
                      <div className="row wrap" style={{ gap: 6, marginTop: 6 }}>
                        <span className="cell-secondary">{h.duration_seconds ? formatDuration(h.duration_seconds) : 'Duration not reported'}</span>
                        {h.analysis_available && <LevelBadge level={h.interest_level} prefix="Interest" />}
                        {h.analysis_available && <LevelBadge level={h.purchase_intent} prefix="Intent" />}
                        {h.objection_categories.map((c) => <span key={c} className="badge badge-warning">⚠ {OBJECTION_LABELS[c] || c}</span>)}
                      </div>
                    </div>
                    {h.follow_up_required && <span className="badge badge-accent">Follow-up</span>}
                  </Link>
                ))}
              </div>
            )}
          </Card>

          {a?.history.filter((h) => h.analysis_available).length > 1 && (
            <Card title="Signals over time" subtitle="How interest, intent and objections changed across meetings (no causal claims)" badge={<span className="badge badge-ai badge-sm"><Sparkles size={10} /> AI</span>} flush>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Meeting</th><th>Date</th><th>Duration</th><th>Engagement</th><th>Interest</th><th>Intent</th><th>Objections</th></tr></thead>
                  <tbody>
                    {a.history.filter((h) => h.analysis_available).map((h) => (
                      <tr key={h.meeting_id}>
                        <td className="cell-primary">{h.label}</td>
                        <td>{formatDate(h.start_time)}</td>
                        <td className="tabular">{formatDuration(h.duration_seconds)}</td>
                        <td><LevelBadge level={h.engagement_level} /></td>
                        <td><LevelBadge level={h.interest_level} /></td>
                        <td><LevelBadge level={h.purchase_intent} /></td>
                        <td>{h.objection_categories.map((c) => OBJECTION_LABELS[c] || c).join(', ') || <span className="muted">None</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          <Card title="Follow-up history" icon={ListChecks}>
            {!a ? <SkeletonCard lines={2} /> : !a.follow_up_history.length ? <p className="muted">No follow-ups yet.</p> : (
              <div className="list">
                {a.follow_up_history.map((f) => (
                  <div key={f.id} className="list-item">
                    <span className={`badge ${f.status === 'completed' ? 'badge-success' : f.status === 'snoozed' ? 'badge-info' : 'badge-warning'}`}>{f.status}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="cell-primary row" style={{ gap: 6 }}>{f.recommended_action} {f.ai_generated && <span className="badge badge-ai badge-sm"><Sparkles size={10} /> AI recommendation</span>}</div>
                      <div className="cell-secondary">{f.reason}</div>
                    </div>
                    <span className="cell-secondary">Due {formatDate(f.due_date)}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
        <div className="stack">
          <LeadIntelligenceCard intel={a?.intelligence} />
          <Card title="Lead journey" subtitle="Every event with its time and source">
            {!a ? <SkeletonCard lines={4} /> : <Timeline events={journey} />}
          </Card>
        </div>
      </div>

      {l && <LeadFormModal open={editing} lead={l} onClose={() => setEditing(false)} onSaved={refresh} />}
      {l && <ScheduleMeetingModal open={scheduling} lead={l} onClose={() => setScheduling(false)} onScheduled={refresh} />}
    </div>
  );
}
