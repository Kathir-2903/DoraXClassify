import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, AlertOctagon, Brain, CheckCircle2, FileText, Loader2, Mic, RefreshCw, Webhook } from 'lucide-react';
import { useAsync } from '../../hooks/useAsync';
import { usePolling } from '../../hooks/usePolling';
import { useToast } from '../../hooks/useToast';
import { adminApi } from '../../services/analyticsApi';
import { errorText } from '../../services/api';
import { KpiCard } from '../../components/cards/KpiCard';
import { DataTable, Pagination } from '../../components/tables/DataTable';
import { DemoBadge, StageBadge } from '../../components/badges/Badge';
import { EmptyState, ErrorState } from '../../components/common/States';
import { MiniPipeline } from '../../components/meeting/MiniPipeline';
import { formatDateTime, relativeTime } from '../../utils/date';

const FILTERS = [['attention', 'Needs attention'], ['failed', 'Failed'], ['processing', 'In progress'], ['all', 'All completed meetings']];
const STAGE_LABEL = { recording: 'Recording', transcript: 'Transcript', analysis: 'AI Analysis' };

export default function AdminProcessing() {
  const toast = useToast();
  const [filter, setFilter] = useState('attention');
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState('');
  const { data, loading, error, refetch } = useAsync(() => adminApi.processing({ filter, page, page_size: 25 }), [filter, page]);
  usePolling(() => refetch({ silent: true }), true, 10000);
  const c = data?.cards;

  const retry = async (row) => {
    setBusy(row.meeting_id);
    try {
      await adminApi.retry(row.meeting_id, row.stage);
      toast.success('Retry queued', `${STAGE_LABEL[row.stage]} for ${row.lead}`);
      refetch({ silent: true });
    } catch (err) {
      toast.error('Retry failed', errorText(err));
    } finally {
      setBusy('');
    }
  };

  if (error) return <div className="page"><ErrorState error={error} onRetry={refetch} /></div>;
  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Processing Monitor</h1>
          <p className="subtitle">Recording → Transcript → AI Analysis · refreshes every 10 seconds · max 3 automatic attempts per stage</p>
        </div>
        <button className="btn" onClick={() => refetch()}><RefreshCw /> Refresh</button>
      </div>
      <div className="kpi-grid" style={{ marginBottom: 16, '--kpi-cols': 6 }}>
        <KpiCard loading={loading && !c} label="Recordings Processing" value={c?.recordings_processing} icon={Mic} tone="accent" />
        <KpiCard loading={loading && !c} label="Transcripts Processing" value={c?.transcripts_processing} icon={FileText} tone="accent" />
        <KpiCard loading={loading && !c} label="AI Analysis Processing" value={c?.analysis_processing} icon={Brain} tone="ai" />
        <KpiCard loading={loading && !c} label="Queued" value={c?.queued} icon={Activity} />
        <KpiCard loading={loading && !c} label="Failed Jobs" value={c?.failed_jobs} icon={AlertOctagon} tone={c?.failed_jobs ? 'error' : 'default'} />
        <Link to="/admin/webhooks"><KpiCard loading={loading && !c} label="Webhook Errors" value={c?.webhook_errors} icon={Webhook} tone={c?.webhook_errors ? 'warning' : 'default'} /></Link>
      </div>
      <div className="card">
        <div className="toolbar">
          <div className="chip-tabs">
            {FILTERS.map(([v, l]) => <button key={v} className={`chip-tab ${filter === v ? 'active' : ''}`} onClick={() => { setFilter(v); setPage(1); }}>{l}</button>)}
          </div>
        </div>
        <DataTable columns={[
          { key: 'meeting', header: 'Meeting', sticky: true, mobileLabel: '', render: (r) => <Link to={`/meetings/${r.meeting_id}`}><span className="cell-primary row" style={{ gap: 6 }}>{r.label} {r.is_demo && <DemoBadge />}</span><span className="cell-secondary">{r.sales_person}</span></Link> },
          { key: 'lead', header: 'Lead', render: (r) => <Link className="link" to={`/leads/${r.lead_id}`}>{r.lead}</Link> },
          { key: 'pipeline', header: 'Pipeline', render: (r) => <MiniPipeline processing={Object.fromEntries(Object.entries(r.stages).map(([k, v]) => [k, { status: v }]))} completed /> },
          { key: 'stage', header: 'Stage', render: (r) => STAGE_LABEL[r.stage] },
          { key: 'status', header: 'Status', render: (r) => <StageBadge status={r.status} /> },
          { key: 'started', header: 'Started', render: (r) => (r.started_at ? <span title={formatDateTime(r.started_at)}>{relativeTime(r.started_at)}</span> : <span className="muted">—</span>) },
          { key: 'attempts', header: 'Attempts', render: (r) => <span className="tabular">{r.attempts} / 3</span> },
          { key: 'error', header: 'Last Error', className: 'wrap-cell', render: (r) => (r.last_error ? <span style={{ color: 'var(--error)' }}>{r.last_error}</span> : <span className="muted">—</span>) },
          {
            key: 'retry', header: '', mobileLabel: '',
            render: (r) => r.status === 'failed' && (
              <button className="btn btn-sm" onClick={() => retry(r)} disabled={busy === r.meeting_id}>{busy === r.meeting_id ? <Loader2 className="spin" /> : <RefreshCw />} Retry</button>
            ),
          },
        ]} rows={data?.items} rowKey={(r) => r.meeting_id} loading={loading}
           empty={<EmptyState icon={CheckCircle2} title="Nothing needs attention" description="All recordings, transcripts and AI analyses are processed." />} />
        {data?.total > 0 && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
      </div>
    </div>
  );
}
