import { useCallback, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { CalendarCheck2, Download, Loader2, Mail, Search, X } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { useDebounce } from '../../hooks/useDebounce';
import { useMeetings } from '../../hooks/useMeetings';
import { useSalesPeople } from '../../hooks/useLeads';
import { useToast } from '../../hooks/useToast';
import { meetingApi } from '../../services/meetingApi';
import { errorText } from '../../services/api';
import { DataTable, Pagination } from '../../components/tables/DataTable';
import { DemoBadge, LevelBadge, StatusBadge } from '../../components/badges/Badge';
import { EmptyState, ErrorState } from '../../components/common/States';
import { MiniPipeline } from '../../components/meeting/MiniPipeline';
import { formatDuration } from '../../utils/formatting';
import { formatDateTime } from '../../utils/date';
import { MEETING_STATUS_FILTERS } from '../../utils/status';

const TABS = [{ value: '', label: 'All' }, ...MEETING_STATUS_FILTERS];

function channelIcon(state, Icon, label) {
  const s = state?.status;
  const color = s === 'sent' || s === 'delivered' ? 'var(--success)' : s === 'failed' ? 'var(--error)' : 'var(--text-3)';
  return <Icon size={14} color={color} aria-label={`${label}: ${s || 'pending'}`} title={`${label}: ${s || 'pending'}`} />;
}

export default function Meetings() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [sp, setSp] = useSearchParams();
  const [search, setSearch] = useState(sp.get('q') || '');
  const [exporting, setExporting] = useState(false);
  const q = useDebounce(search, 300);
  const { data: salesPeople } = useSalesPeople();

  const params = useMemo(() => ({
    q,
    status: sp.get('status') || '',
    sales_person_id: sp.get('sales_person_id') || '',
    lead_id: sp.get('lead_id') || '',
    date_from: sp.get('date_from') || '',
    date_to: sp.get('date_to') || '',
    page: Number(sp.get('page') || 1),
    page_size: 20,
  }), [q, sp]);
  const { data, loading, error, refetch } = useMeetings(params);

  const update = useCallback((changes) => {
    const next = new URLSearchParams(sp);
    Object.entries(changes).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    if (!('page' in changes)) next.delete('page');
    setSp(next, { replace: true });
  }, [sp, setSp]);

  const exportCsv = async () => {
    setExporting(true);
    try {
      const { page, page_size, lead_id, ...filters } = params;
      await meetingApi.exportCsv(filters);
      toast.success('Export ready', 'Meetings CSV downloaded.');
    } catch (err) {
      toast.error('Export failed', errorText(err));
    } finally {
      setExporting(false);
    }
  };

  const columns = [
    {
      key: 'meeting', header: 'Meeting', sticky: true, mobileLabel: '',
      render: (m) => (
        <Link to={`/meetings/${m.id}`}>
          <span className="cell-primary row" style={{ gap: 6 }}>{m.lead_snapshot?.name} {m.is_demo && <DemoBadge />}</span>
          <span className="cell-secondary">{m.label}</span>
        </Link>
      ),
    },
    { key: 'sp', header: 'Sales Person', render: (m) => m.sales_person_snapshot?.name },
    { key: 'when', header: 'Scheduled (IST)', render: (m) => <span className="tabular">{formatDateTime(m.schedule.start_time)}</span> },
    { key: 'status', header: 'Status', render: (m) => <StatusBadge state={m.status.overall} /> },
    { key: 'duration', header: 'Duration', render: (m) => (m.attendance?.duration_seconds ? <span className="tabular">{formatDuration(m.attendance.duration_seconds)}</span> : <span className="muted">{m.schedule.duration_minutes} min planned</span>) },
    { key: 'invites', header: 'Invites', render: (m) => <span className="row" style={{ gap: 8 }}>{channelIcon(m.notifications?.email, Mail, 'Email')}</span> },
    { key: 'pipeline', header: 'Processing', render: (m) => <MiniPipeline processing={m.processing} completed={m.status.meeting_completed && !m.status.no_show} /> },
    { key: 'interest', header: 'Interest', render: (m) => <LevelBadge level={m.analysis?.snapshot?.interest_level} /> },
    { key: 'objection', header: 'Main Objection', render: (m) => m.analysis?.snapshot?.main_objection || <span className="muted">—</span> },
    { key: 'follow', header: 'Follow-up', render: (m) => (m.status.follow_up_required ? <span className="badge badge-warning">Required</span> : <span className="muted">—</span>) },
  ];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Meetings</h1>
          <p className="subtitle">Every Classify meeting and what came out of it</p>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={exportCsv} disabled={exporting}>{exporting ? <Loader2 className="spin" /> : <Download />} Export Meetings CSV</button>
          {!isAdmin && <Link className="btn btn-primary" to="/leads"><CalendarCheck2 /> Schedule Video Call</Link>}
        </div>
      </div>
      <div className="card">
        <div className="toolbar">
          <div className="chip-tabs" role="tablist" aria-label="Status">
            {TABS.map((t) => (
              <button key={t.label} className={`chip-tab ${params.status === t.value ? 'active' : ''}`} role="tab" aria-selected={params.status === t.value} onClick={() => update({ status: t.value })}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
        <div className="toolbar">
          <div className="input-icon search">
            <Search />
            <input className="input" placeholder="Search lead, label, sales person, meeting ID" value={search} onChange={(e) => { setSearch(e.target.value); update({ q: e.target.value }); }} aria-label="Search meetings" />
          </div>
          {isAdmin && (
            <select className="select" value={params.sales_person_id} onChange={(e) => update({ sales_person_id: e.target.value })} aria-label="Sales person">
              <option value="">All sales people</option>
              {(salesPeople || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          )}
          <input type="date" className="input" style={{ width: 145 }} value={params.date_from} onChange={(e) => update({ date_from: e.target.value })} aria-label="From date" />
          <input type="date" className="input" style={{ width: 145 }} value={params.date_to} onChange={(e) => update({ date_to: e.target.value })} aria-label="To date" />
          {params.lead_id && (
            <button className="btn btn-sm" onClick={() => update({ lead_id: '' })}><X /> One lead only</button>
          )}
        </div>
        {error ? <ErrorState error={error} onRetry={refetch} /> : (
          <DataTable caption="Meetings" columns={columns} rows={data?.items} loading={loading} onRowClick={(m) => navigate(`/meetings/${m.id}`)}
                     empty={<EmptyState icon={CalendarCheck2} title="No meetings yet" description="Schedule your first Classify meeting to start capturing sales intelligence."
                                        action={<Link className="btn btn-primary btn-sm" to="/leads">Choose a lead</Link>} />} />
        )}
        {data?.total > 0 && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => update({ page: String(p) })} />}
      </div>
    </div>
  );
}
