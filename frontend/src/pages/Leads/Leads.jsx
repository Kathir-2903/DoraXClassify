import { useCallback, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { CalendarCheck2, CalendarPlus, Download, Eye, Filter, Loader2, Pencil, Plus, Search, Users, X } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { useDebounce } from '../../hooks/useDebounce';
import { useLeads, useSalesPeople } from '../../hooks/useLeads';
import { useSettings } from '../../hooks/useAnalytics';
import { useToast } from '../../hooks/useToast';
import { leadApi } from '../../services/leadApi';
import { errorText } from '../../services/api';
import { DataTable, Pagination } from '../../components/tables/DataTable';
import { AIBadge, DemoBadge, LeadStatusBadge, LevelBadge, StatusBadge } from '../../components/badges/Badge';
import { EmptyState, ErrorState } from '../../components/common/States';
import { RowMenu } from '../../components/common/RowMenu';
import { LeadFormModal } from '../../components/modals/LeadFormModal';
import { ScheduleMeetingModal } from '../../components/modals/ScheduleMeetingModal';
import { formatDuration, initials } from '../../utils/formatting';
import { formatDate, relativeTime } from '../../utils/date';
import { LEAD_STATUSES, MEETING_STATES } from '../../utils/status';

const FILTER_KEYS = ['sales_person_id', 'meeting_status', 'lead_status', 'interest', 'intent', 'follow_up', 'lead_source', 'date_from', 'date_to'];

export default function Leads() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [sp, setSp] = useSearchParams();
  const [search, setSearch] = useState(sp.get('q') || '');
  const [showFilters, setShowFilters] = useState(FILTER_KEYS.some((k) => sp.get(k)));
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);
  const [scheduling, setScheduling] = useState(null);
  const [exporting, setExporting] = useState(false);
  const q = useDebounce(search, 300);
  const { data: salesPeople } = useSalesPeople();
  const { data: settings } = useSettings();

  const params = useMemo(() => {
    const p = { q, page: Number(sp.get('page') || 1), page_size: 20, sort: sp.get('sort') || 'last_activity', order: sp.get('order') || 'desc' };
    FILTER_KEYS.forEach((k) => { if (sp.get(k)) p[k] = sp.get(k); });
    return p;
  }, [q, sp]);

  const { data, loading, error, refetch } = useLeads(params);

  const update = useCallback((changes) => {
    const next = new URLSearchParams(sp);
    Object.entries(changes).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    if (!('page' in changes)) next.delete('page');
    setSp(next, { replace: true });
  }, [sp, setSp]);

  const onSort = (key) => update({ sort: key, order: params.sort === key && params.order === 'desc' ? 'asc' : 'desc', page: undefined });
  const activeFilters = FILTER_KEYS.filter((k) => sp.get(k)).length;

  const exportCsv = async () => {
    setExporting(true);
    try {
      const { page, page_size, sort, order, ...filters } = params;
      await leadApi.exportCsv(filters);
      toast.success('Export ready', 'Leads CSV downloaded.');
    } catch (err) {
      toast.error('Export failed', errorText(err));
    } finally {
      setExporting(false);
    }
  };

  const columns = [
    {
      key: 'name', header: 'Name', sortKey: 'name', sticky: true, mobileLabel: '',
      render: (l) => (
        <Link to={`/leads/${l.id}`} className="row" style={{ gap: 10 }}>
          <span className="avatar avatar-sm">{initials(l.name)}</span>
          <span>
            <span className="cell-primary row" style={{ gap: 6 }}>{l.name} {l.is_demo && <DemoBadge />}</span>
            <span className="cell-secondary">{l.interested_product || l.lead_source || '—'}</span>
          </span>
        </Link>
      ),
    },
    { key: 'email', header: 'Email', sortKey: 'email', render: (l) => l.email },
    { key: 'phone', header: 'Phone', render: (l) => <span className="tabular">{l.phone}</span> },
    { key: 'company', header: 'Company', sortKey: 'company', render: (l) => l.company || <span className="muted">—</span> },
    { key: 'sp', header: 'Assigned Sales Person', render: (l) => l.sales_person?.name || '—' },
    { key: 'source', header: 'Lead Source', render: (l) => l.lead_source || <span className="muted">—</span> },
    { key: 'created', header: 'Created', sortKey: 'created_at', render: (l) => formatDate(l.created_at) },
    { key: 'meetings', header: 'Meetings', sortKey: 'meetings', render: (l) => <span className="tabular">{l.intelligence?.meetings_count ?? 0}</span> },
    { key: 'last_meeting', header: 'Last Meeting', sortKey: 'last_meeting', render: (l) => (l.intelligence?.last_meeting_at ? formatDate(l.intelligence.last_meeting_at) : <span className="muted">—</span>) },
    { key: 'meeting_status', header: 'Meeting Status', render: (l) => (l.intelligence?.last_meeting_status ? <StatusBadge state={l.intelligence.last_meeting_status} /> : <span className="muted">No meetings</span>) },
    { key: 'duration', header: 'Last Duration', sortKey: 'last_duration', render: (l) => <span className="tabular">{formatDuration(l.intelligence?.last_duration_seconds)}</span> },
    { key: 'status', header: 'Lead Status', sortKey: 'lead_status', render: (l) => <LeadStatusBadge status={l.lead_status} /> },
    { key: 'engagement', header: 'Engagement', render: (l) => <LevelBadge level={l.intelligence?.engagement_level} /> },
    { key: 'interest', header: 'Interest', sortKey: 'interest', render: (l) => <LevelBadge level={l.intelligence?.interest_level} /> },
    { key: 'intent', header: 'Intent', sortKey: 'intent', render: (l) => <LevelBadge level={l.intelligence?.purchase_intent} /> },
    {
      key: 'follow', header: 'Follow-up',
      render: (l) => (l.intelligence?.follow_up_required
        ? <span className="badge badge-warning">Due {formatDate(l.intelligence.follow_up_due)}</span>
        : <span className="muted">—</span>),
    },
    {
      key: 'analysis', header: 'Analysis',
      render: (l) => {
        const s = l.intelligence?.analysis_status;
        if (!s) return <span className="muted">—</span>;
        const map = { completed: ['success', 'Complete'], processing: ['accent', 'Processing'], pending: ['neutral', 'Pending'], failed: ['error', 'Failed'], skipped: ['neutral', 'No show'], unavailable: ['warning', 'Unavailable'] };
        const [tone, label] = map[s] || ['neutral', s];
        return <span className={`badge badge-${tone}`}>{label}</span>;
      },
    },
    { key: 'activity', header: 'Last Activity', sortKey: 'last_activity', render: (l) => <span className="muted">{relativeTime(l.last_activity_at)}</span> },
    {
      key: 'actions', header: '', mobileLabel: '', stickyRight: true,
      render: (l) => (
        <div className="row" style={{ gap: 4 }}>
          {!isAdmin && (
            <button className="btn btn-sm" onClick={() => setScheduling(l)} aria-label={`Schedule Video Call with ${l.name}`}>
              <CalendarPlus /> <span>Schedule</span>
            </button>
          )}
          <RowMenu items={[
            { label: 'View', icon: Eye, onClick: () => navigate(`/leads/${l.id}`) },
            !isAdmin && { label: 'Schedule Meeting', icon: CalendarPlus, onClick: () => setScheduling(l) },
            isAdmin && { label: 'Edit', icon: Pencil, onClick: () => setEditing(l) },
            { label: 'View Meetings', icon: CalendarCheck2, onClick: () => navigate(`/meetings?lead_id=${l.id}`) },
          ]} />
        </div>
      ),
    },
  ];

  const sel = (key, label, options, width = 150) => (
    <select className="select" style={{ width }} value={sp.get(key) || ''} onChange={(e) => update({ [key]: e.target.value })} aria-label={label}>
      <option value="">{label}</option>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );
  const levels = [['high', 'High'], ['medium', 'Medium'], ['low', 'Low'], ['unknown', 'Unknown']];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Leads</h1>
          <p className="subtitle">{data ? `${data.total} lead${data.total === 1 ? '' : 's'}` : 'Loading…'} · AI columns (Engagement, Interest, Intent) come from meeting analysis</p>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={exportCsv} disabled={exporting}>{exporting ? <Loader2 className="spin" /> : <Download />} Export CSV</button>
          {isAdmin && <button className="btn btn-primary" onClick={() => setCreating(true)}><Plus /> Add Lead</button>}
        </div>
      </div>

      <div className="card">
        <div className="toolbar">
          <div className="input-icon search">
            <Search />
            <input className="input" placeholder="Search name, email, phone, company" value={search} onChange={(e) => { setSearch(e.target.value); update({ q: e.target.value }); }} aria-label="Search leads" />
          </div>
          <button className={`btn btn-sm ${showFilters ? 'btn-dark' : ''}`} onClick={() => setShowFilters((s) => !s)}>
            <Filter /> Filters {activeFilters ? `(${activeFilters})` : ''}
          </button>
          {activeFilters > 0 && (
            <button className="btn btn-sm btn-ghost" onClick={() => { const n = new URLSearchParams(); if (search) n.set('q', search); setSp(n); }}>
              <X /> Clear
            </button>
          )}
          <span style={{ marginLeft: 'auto' }}><AIBadge label="Interest & intent are AI generated" /></span>
        </div>
        {showFilters && (
          <div className="toolbar" style={{ background: 'var(--surface-2)' }}>
            {isAdmin && sel('sales_person_id', 'Sales person', (salesPeople || []).map((s) => [s.id, s.name]), 160)}
            {sel('meeting_status', 'Meeting status', Object.entries(MEETING_STATES).filter(([k]) => k !== 'DRAFT' && k !== 'INVITATION_SENT').map(([k, v]) => [k, v.label]), 170)}
            {sel('lead_status', 'Lead status', Object.entries(LEAD_STATUSES).map(([k, v]) => [k, v.label]))}
            {sel('interest', 'Interest', levels, 120)}
            {sel('intent', 'Intent', levels, 120)}
            {sel('follow_up', 'Follow-up', [['true', 'Required'], ['false', 'Not required']], 130)}
            {sel('lead_source', 'Source', (settings?.lead_sources || []).map((s) => [s, s]), 130)}
            <label className="row" style={{ gap: 6, fontSize: 12 }}>
              Created
              <input type="date" className="input" style={{ width: 140 }} value={sp.get('date_from') || ''} onChange={(e) => update({ date_from: e.target.value })} aria-label="Created from" />
              –
              <input type="date" className="input" style={{ width: 140 }} value={sp.get('date_to') || ''} onChange={(e) => update({ date_to: e.target.value })} aria-label="Created to" />
            </label>
          </div>
        )}
        {error ? (
          <ErrorState error={error} onRetry={refetch} />
        ) : (
          <DataTable
            caption="Leads"
            columns={columns}
            rows={data?.items}
            loading={loading}
            sort={{ key: params.sort, order: params.order }}
            onSort={onSort}
            onRowClick={(l) => navigate(`/leads/${l.id}`)}
            empty={
              q || activeFilters ? (
                <EmptyState icon={Search} title="No leads match" description="Try a different search or clear the filters." />
              ) : (
                <EmptyState icon={Users} title="No leads yet" description="Add your first lead, then schedule a Classify meeting to start capturing sales intelligence."
                            action={isAdmin && <button className="btn btn-primary" onClick={() => setCreating(true)}><Plus /> Add Lead</button>} />
              )
            }
          />
        )}
        {data?.total > 0 && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => update({ page: String(p) })} />}
      </div>

      <LeadFormModal open={creating || Boolean(editing)} lead={editing} onClose={() => { setCreating(false); setEditing(null); }} onSaved={() => refetch({ silent: true })} />
      <ScheduleMeetingModal open={Boolean(scheduling)} lead={scheduling} onClose={() => setScheduling(null)} onScheduled={() => refetch({ silent: true })} />
    </div>
  );
}
