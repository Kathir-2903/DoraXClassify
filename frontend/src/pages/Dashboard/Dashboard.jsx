import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  AlertOctagon, ArrowRight, BrainCircuit, CalendarCheck2, CalendarClock, CalendarDays, CheckCircle2, Clock3, FileWarning,
  ListChecks, MicOff, Plus, Sparkles, UserCheck, UserX, Users,
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { useDashboard } from '../../hooks/useAnalytics';
import { useSalesPeople } from '../../hooks/useLeads';
import { useAsync } from '../../hooks/useAsync';
import { meetingApi } from '../../services/meetingApi';
import { KpiCard } from '../../components/cards/KpiCard';
import { Card } from '../../components/cards/Card';
import { InsightCards } from '../../components/cards/InsightCards';
import { ChartCard } from '../../components/charts/ChartCard';
import { DonutChart, LEVEL_COLORS, SimpleBarChart, STATUS_COLORS, TimeSeriesChart } from '../../components/charts/Charts';
import { AIBadge, LevelBadge, StatusBadge } from '../../components/badges/Badge';
import { EmptyState, ErrorState } from '../../components/common/States';
import { Skeleton } from '../../components/common/Skeleton';
import { LeadFormModal } from '../../components/modals/LeadFormModal';
import { formatDuration, formatNumber, formatPercent, initials } from '../../utils/formatting';
import { formatShortDate, formatWeekday, formatTime, greeting } from '../../utils/date';

function HealthStrip({ o }) {
  const items = [
    { label: 'No Shows', value: o?.no_shows, icon: UserX, color: 'var(--status-serious)' },
    { label: 'Recording Failures', value: o?.recording_failures, icon: MicOff, color: 'var(--status-critical)' },
    { label: 'Transcript Failures', value: o?.transcript_failures, icon: FileWarning, color: 'var(--status-critical)' },
    { label: 'AI Processing Failures', value: o?.ai_failures, icon: AlertOctagon, color: 'var(--status-critical)' },
  ];
  return (
    <div className="health-strip" role="list" aria-label="Exceptions">
      {items.map((it) => (
        <div className="health-item" role="listitem" key={it.label}>
          <it.icon style={{ color: it.value ? it.color : 'var(--text-3)' }} aria-hidden="true" />
          {it.label}
          <strong className="tabular">{it.value ?? '—'}</strong>
        </div>
      ))}
    </div>
  );
}

function IntelligenceFeed({ salesPersonId }) {
  const { data, loading } = useAsync(
    () => meetingApi.list({ analysis_status: 'completed', page_size: 5, sales_person_id: salesPersonId }),
    [salesPersonId],
    { key: `feed:${salesPersonId || 'all'}` },
  );
  const items = data?.items || [];
  return (
    <Card title="Latest meeting intelligence" subtitle="What happened, what the lead cares about, what to do next" badge={<AIBadge />}
          actions={<Link className="btn btn-sm btn-ghost" to="/meetings?status=MEETING_COMPLETED,ANALYSIS_COMPLETED,FOLLOW_UP_REQUIRED,CLOSED">All <ArrowRight /></Link>}>
      {loading && !items.length ? (
        [0, 1, 2].map((i) => <div key={i} style={{ padding: '10px 0' }}><Skeleton width="50%" /><div style={{ height: 8 }} /><Skeleton width="90%" height={10} /></div>)
      ) : !items.length ? (
        <EmptyState icon={BrainCircuit} title="No analysed meetings yet" description="Completed meetings are analysed automatically — insights appear here." />
      ) : (
        items.map((m) => {
          const s = m.analysis?.snapshot || {};
          return (
            <Link key={m.id} to={`/meetings/${m.id}`} className="feed-item">
              <span className="avatar">{initials(m.lead_snapshot?.name)}</span>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div className="row-between">
                  <span className="cell-primary">{m.lead_snapshot?.name}</span>
                  <span className="cell-secondary">{formatShortDate(m.schedule.start_time)}</span>
                </div>
                <p className="feed-summary">{s.summary}</p>
                <div className="row wrap" style={{ gap: 6 }}>
                  <LevelBadge level={s.interest_level} prefix="Interest" />
                  <LevelBadge level={s.purchase_intent} prefix="Intent" />
                  {s.main_objection && <span className="badge badge-warning">⚠ {s.main_objection}</span>}
                  {s.follow_up_required && <span className="badge badge-accent">Follow-up</span>}
                </div>
              </div>
            </Link>
          );
        })
      )}
    </Card>
  );
}

function Upcoming({ salesPersonId }) {
  const nowIso = useMemo(() => new Date().toISOString(), []);
  const { data, loading } = useAsync(
    () => meetingApi.list({ status: 'SCHEDULED,INVITATION_SENT,WAITING_FOR_LEAD', date_from: nowIso, order: 'asc', page_size: 5, sales_person_id: salesPersonId }),
    [salesPersonId],
    { key: `upcoming:${salesPersonId || 'all'}` },
  );
  const items = data?.items || [];
  return (
    <Card title="Upcoming meetings" icon={CalendarClock}>
      {loading && !items.length ? (
        <Skeleton height={120} />
      ) : !items.length ? (
        <EmptyState icon={CalendarDays} title="No meetings scheduled" description="Schedule your first Classify meeting to start capturing sales intelligence." action={<Link className="btn btn-primary btn-sm" to="/leads">Go to leads</Link>} />
      ) : (
        <div className="list">
          {items.map((m) => (
            <Link key={m.id} to={`/meetings/${m.id}`} className="list-item">
              <div className="seq-pill tabular" style={{ minWidth: 76 }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{formatWeekday(m.schedule.start_time)}</div>
                {formatTime(m.schedule.start_time)}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="cell-primary">{m.lead_snapshot?.name}</div>
                <div className="cell-secondary">{m.sales_person_snapshot?.name} · {m.schedule.duration_minutes} min</div>
              </div>
              <StatusBadge state={m.status.overall} />
            </Link>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function Dashboard() {
  const { user, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [salesPersonId, setSalesPersonId] = useState('');
  const [leadModal, setLeadModal] = useState(false);
  const { data: salesPeople } = useSalesPeople();
  const d = useDashboard(salesPersonId || undefined);
  const o = d.overview.data;
  const charts = d.meetings.data;
  const eng = d.engagement.data;
  const fu = d.followups.data;

  if (d.overview.error) return <div className="page"><ErrorState error={d.overview.error} onRetry={d.overview.refetch} /></div>;

  const series = charts?.meetings_over_time || [];
  const statusTotal = (charts?.status_breakdown || []).reduce((s, x) => s + x.value, 0);
  const durationTotal = (charts?.duration_distribution || []).reduce((s, x) => s + x.count, 0);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>{greeting()}, {user?.name?.split(' ')[0]}</h1>
          <p className="subtitle">{isAdmin ? 'Company-wide sales meeting intelligence' : 'Your meetings, leads and next actions'} · Asia/Kolkata</p>
        </div>
        <div className="page-actions">
          {isAdmin && (
            <select className="select" style={{ width: 200 }} value={salesPersonId} onChange={(e) => setSalesPersonId(e.target.value)} aria-label="Filter by sales person">
              <option value="">All sales people</option>
              {(salesPeople || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          )}
          {isAdmin && <button className="btn" onClick={() => setLeadModal(true)}><Plus /> Add Lead</button>}
          {!isAdmin && <Link className="btn btn-primary" to="/leads"><CalendarCheck2 /> Schedule Video Call</Link>}
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 12 }}>
        <KpiCard loading={d.overview.loading} label="Total Leads" value={formatNumber(o?.total_leads)} icon={Users} onClick={() => navigate('/leads')} />
        <KpiCard loading={d.overview.loading} label="Meetings Scheduled" value={formatNumber(o?.meetings_scheduled)} hint={o ? `${o.meetings_upcoming} upcoming` : ''} icon={CalendarClock} tone="accent" onClick={() => navigate('/meetings')} />
        <KpiCard loading={d.overview.loading} label="Meetings Completed" value={formatNumber(o?.meetings_completed)} icon={CheckCircle2} tone="success" />
        <KpiCard loading={d.overview.loading} label="Meetings Today" value={formatNumber(o?.meetings_today)} icon={CalendarDays} />
        <KpiCard loading={d.overview.loading} label="Lead Join Rate" value={o?.lead_join_rate == null ? 'No data' : formatPercent(o.lead_join_rate)} hint={o?.lead_join_sample ? `from ${o.lead_join_sample} meetings with attendance` : 'Needs attendance data'} icon={UserCheck} tone="success" />
        <KpiCard loading={d.overview.loading} label="Avg Meeting Duration" value={formatDuration(o?.average_meeting_duration_seconds)} hint="Reported by Classify" icon={Clock3} />
        <KpiCard loading={d.overview.loading} label="Follow-ups Required" value={formatNumber(o?.follow_ups_required)} hint={fu?.overdue ? `${fu.overdue} overdue` : 'Open follow-ups'} icon={ListChecks} tone="warning" />
        <KpiCard loading={d.overview.loading} label="Analysis Completed" value={formatNumber(o?.analysis_completed)} hint={o?.processing_now ? `${o.processing_now} processing now` : 'AI-analysed meetings'} icon={Sparkles} tone="ai" />
      </div>
      <div style={{ marginBottom: 16 }}><HealthStrip o={o} /></div>

      <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)', marginBottom: 16 }} data-responsive="split">
        <ChartCard title="Meetings over time" subtitle="Last 30 days, by scheduled date" loading={d.meetings.loading} empty={!series.some((r) => r.scheduled)}
                   emptyText="No meetings in the last 30 days." height={270}
                   table={{ columns: ['Date', 'Scheduled', 'Completed', 'No show'], rows: series.map((r) => [r.date, r.scheduled, r.completed, r.no_show]) }}>
          <TimeSeriesChart data={series} height={270} xFormatter={(v) => formatShortDate(`${v}T12:00:00+05:30`)}
                           series={[{ key: 'scheduled', label: 'Scheduled' }, { key: 'completed', label: 'Completed' }, { key: 'no_show', label: 'No show' }]} />
        </ChartCard>
        <ChartCard title="Meeting status" loading={d.meetings.loading} empty={!statusTotal} height={270}
                   table={{ columns: ['Status', 'Meetings'], rows: (charts?.status_breakdown || []).map((r) => [r.name, r.value]) }}>
          <DonutChart data={charts?.status_breakdown || []} colors={STATUS_COLORS} height={230} centerLabel="meetings" />
        </ChartCard>
      </div>

      <div className="grid grid-3" style={{ marginBottom: 16 }}>
        <ChartCard title="Lead engagement" subtitle={eng ? `${eng.sample_size} analysed meetings` : ''} ai loading={d.engagement.loading} empty={!eng?.sample_size}
                   emptyText="Engagement appears once meetings are analysed." height={220}
                   table={{ columns: ['Engagement', 'Meetings'], rows: (eng?.engagement || []).map((r) => [r.level, r.count]) }}>
          <SimpleBarChart data={eng?.engagement || []} xKey="level" yKey="count" name="Meetings" colors={LEVEL_COLORS} height={220} />
        </ChartCard>
        <ChartCard title="Meeting duration" subtitle="Completed meetings" loading={d.meetings.loading} empty={!durationTotal} height={220}
                   table={{ columns: ['Duration', 'Meetings'], rows: (charts?.duration_distribution || []).map((r) => [r.bucket, r.count]) }}>
          <SimpleBarChart data={charts?.duration_distribution || []} xKey="bucket" yKey="count" name="Meetings" height={220} />
        </ChartCard>
        <ChartCard title="Follow-up pipeline" loading={d.followups.loading} empty={!(fu?.pipeline || []).some((p) => p.count)} height={220}
                   table={{ columns: ['Stage', 'Count'], rows: (fu?.pipeline || []).map((r) => [r.stage, r.count]) }}>
          <SimpleBarChart data={fu?.pipeline || []} xKey="stage" yKey="count" name="Follow-ups" horizontal height={200} />
        </ChartCard>
      </div>

      <Card title="AI insights" subtitle={d.insights.data ? `Across ${d.insights.data.sample_size} analysed meetings — patterns only shown when they recur` : ''} badge={<AIBadge />} className="" >
        {d.insights.loading && !d.insights.data ? <Skeleton height={80} /> : <InsightCards insights={d.insights.data} />}
      </Card>

      <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)', marginTop: 16 }} data-responsive="split">
        <IntelligenceFeed salesPersonId={salesPersonId || undefined} />
        <Upcoming salesPersonId={salesPersonId || undefined} />
      </div>

      <LeadFormModal open={leadModal} onClose={() => setLeadModal(false)} onSaved={(l) => navigate(`/leads/${l.id}`)} />
    </div>
  );
}
