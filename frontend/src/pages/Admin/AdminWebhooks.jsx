import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Eye, Loader2, RefreshCw, Webhook } from 'lucide-react';
import { useAsync } from '../../hooks/useAsync';
import { useToast } from '../../hooks/useToast';
import { adminApi } from '../../services/analyticsApi';
import { errorText } from '../../services/api';
import { DataTable, Pagination } from '../../components/tables/DataTable';
import { EmptyState, ErrorState } from '../../components/common/States';
import { Modal } from '../../components/modals/Modal';
import { formatDateTime } from '../../utils/date';

const STATUS = { processed: 'success', pending: 'neutral', processing: 'accent', failed: 'error', unmatched: 'warning' };
const TABS = [['', 'All'], ['processed', 'Processed'], ['failed', 'Failed'], ['unmatched', 'Unmatched'], ['pending', 'Pending']];

export default function AdminWebhooks() {
  const toast = useToast();
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [view, setView] = useState(null);
  const [busy, setBusy] = useState('');
  const { data, loading, error, refetch } = useAsync(() => adminApi.webhooks({ status, page, page_size: 25 }), [status, page]);

  const reprocess = async (e) => {
    setBusy(e.id);
    try {
      const out = await adminApi.reprocessWebhook(e.id);
      toast.success('Webhook reprocessed', `Result: ${out.processing_status}`);
      refetch({ silent: true });
    } catch (err) {
      toast.error('Reprocess failed', errorText(err));
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Webhook Events</h1>
          <p className="subtitle">Every Classify callback, stored verbatim and deduplicated by event ID</p>
        </div>
        <button className="btn" onClick={() => refetch()}><RefreshCw /> Refresh</button>
      </div>
      <div className="card">
        <div className="toolbar">
          <div className="chip-tabs">
            {TABS.map(([v, l]) => <button key={l} className={`chip-tab ${status === v ? 'active' : ''}`} onClick={() => { setStatus(v); setPage(1); }}>{l}</button>)}
          </div>
        </div>
        {error ? <ErrorState error={error} onRetry={refetch} /> : (
          <DataTable columns={[
            { key: 'received', header: 'Received', render: (e) => <span className="tabular">{formatDateTime(e.received_at)}</span> },
            { key: 'event', header: 'Event ID', render: (e) => <span className="mono" title={e.event_id}>{e.event_id.length > 22 ? `${e.event_id.slice(0, 22)}…` : e.event_id}</span> },
            { key: 'source', header: 'Source', render: (e) => e.source },
            { key: 'uid', header: 'Classify ID', render: (e) => <span className="mono">{e.classify_unique_id ? `${e.classify_unique_id.slice(0, 13)}…` : '—'}</span> },
            { key: 'meeting', header: 'Meeting', render: (e) => (e.meeting_id ? <Link className="link" to={`/meetings/${e.meeting_id}`}>Open</Link> : <span className="muted">—</span>) },
            { key: 'status', header: 'Status', render: (e) => <span className={`badge badge-${STATUS[e.processing_status] || 'neutral'}`}>{e.processing_status}</span> },
            { key: 'attempts', header: 'Attempts', render: (e) => <span className="tabular">{e.attempt_count}</span> },
            { key: 'error', header: 'Error', className: 'wrap-cell', render: (e) => e.error_message ? <span style={{ color: 'var(--error)' }}>{e.error_message}</span> : <span className="muted">—</span> },
            {
              key: 'actions', header: '', mobileLabel: '',
              render: (e) => (
                <div className="row" style={{ gap: 4 }}>
                  <button className="btn btn-sm" onClick={() => setView(e)}><Eye /> Payload</button>
                  {e.processing_status !== 'processed' && (
                    <button className="btn btn-sm" onClick={() => reprocess(e)} disabled={busy === e.id}>{busy === e.id ? <Loader2 className="spin" /> : <RefreshCw />} Reprocess</button>
                  )}
                </div>
              ),
            },
          ]} rows={data?.items} loading={loading}
             empty={<EmptyState icon={Webhook} title="No webhook events" description="Classify posts attendance and recordings to /api/webhooks/classify after each meeting." />} />
        )}
        {data?.total > 0 && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
      </div>
      <Modal open={Boolean(view)} onClose={() => setView(null)} title="Webhook payload" subtitle={view?.event_id} width={760}>
        <pre className="json-view">{view ? JSON.stringify(view.payload, null, 2) : ''}</pre>
      </Modal>
    </div>
  );
}
