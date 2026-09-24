import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, AlertTriangle, Brain, CalendarCheck2, FileText, Mic, Plus, ShieldAlert, Users, UsersRound, Webhook } from 'lucide-react';
import { useAsync } from '../../hooks/useAsync';
import { useToast } from '../../hooks/useToast';
import { adminApi } from '../../services/analyticsApi';
import { parseError } from '../../services/api';
import { KpiCard } from '../../components/cards/KpiCard';
import { Card } from '../../components/cards/Card';
import { DataTable, Pagination } from '../../components/tables/DataTable';
import { DemoBadge } from '../../components/badges/Badge';
import { ErrorState } from '../../components/common/States';
import { Modal } from '../../components/modals/Modal';
import { formatDateTime, relativeTime } from '../../utils/date';
import { initials } from '../../utils/formatting';

function CreateUser({ open, onClose, onCreated }) {
  const toast = useToast();
  const [f, setF] = useState({ name: '', email: '', password: '', role: 'sales', title: '' });
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await adminApi.createUser({ ...f, title: f.title || null });
      toast.success('User created', f.email);
      onCreated();
      onClose();
      setF({ name: '', email: '', password: '', role: 'sales', title: '' });
    } catch (ex) {
      setErr(parseError(ex));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal open={open} onClose={onClose} title="Add user" busy={busy} width={520}
           footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" form="user-form" type="submit" disabled={busy}>Create user</button></>}>
      <form id="user-form" className="form-grid" onSubmit={submit}>
        <div className="field"><label htmlFor="u-name">Name</label><input id="u-name" className="input" value={f.name} onChange={set('name')} required minLength={2} /></div>
        <div className="field"><label htmlFor="u-email">Email</label><input id="u-email" className="input" type="email" value={f.email} onChange={set('email')} required /></div>
        <div className="field"><label htmlFor="u-pass">Temporary password</label><input id="u-pass" className="input" type="password" value={f.password} onChange={set('password')} required minLength={8} /><span className="hint">At least 8 characters</span></div>
        <div className="field"><label htmlFor="u-role">Role</label><select id="u-role" className="select" value={f.role} onChange={set('role')}><option value="sales">Sales Person</option><option value="admin">Admin</option></select></div>
        <div className="field full"><label htmlFor="u-title">Title</label><input id="u-title" className="input" value={f.title} onChange={set('title')} /></div>
        {err && <div className="notice error full">{err.message}{err.fields && Object.values(err.fields).length ? ` — ${Object.values(err.fields)[0]}` : ''}</div>}
      </form>
    </Modal>
  );
}

export default function AdminOverview() {
  const overview = useAsync(() => adminApi.overview(), [], { key: 'admin-overview', ttl: 10000 });
  const users = useAsync(() => adminApi.users(), [], { key: 'admin-users' });
  const [page, setPage] = useState(1);
  const activity = useAsync(() => adminApi.activity({ page, page_size: 15 }), [page]);
  const [creating, setCreating] = useState(false);
  const o = overview.data;

  if (overview.error) return <div className="page"><ErrorState error={overview.error} onRetry={overview.refetch} /></div>;
  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Admin</h1>
          <p className="subtitle">Everything across the workspace — leads, people, meetings, recordings, AI and integrations</p>
        </div>
        <div className="page-actions">
          <Link className="btn" to="/admin/webhooks"><Webhook /> Webhook Events</Link>
          <Link className="btn" to="/admin/processing"><Activity /> Processing Monitor</Link>
        </div>
      </div>
      <div className="kpi-grid" style={{ marginBottom: 16 }}>
        <Link to="/leads"><KpiCard loading={overview.loading} label="All Leads" value={o?.leads} icon={Users} /></Link>
        <KpiCard loading={overview.loading} label="Sales People" value={o?.sales_people} icon={UsersRound} />
        <Link to="/meetings"><KpiCard loading={overview.loading} label="All Meetings" value={o?.meetings} icon={CalendarCheck2} tone="accent" /></Link>
        <KpiCard loading={overview.loading} label="Recordings" value={o?.recordings} icon={Mic} />
        <KpiCard loading={overview.loading} label="Transcripts" value={o?.transcripts} icon={FileText} />
        <KpiCard loading={overview.loading} label="AI Analyses" value={o?.analyses} hint="All versions" icon={Brain} tone="ai" />
        <Link to="/admin/webhooks"><KpiCard loading={overview.loading} label="Webhook Events" value={o?.webhook_events} hint={o?.webhook_errors ? `${o.webhook_errors} need attention` : 'All processed'} icon={Webhook} tone={o?.webhook_errors ? 'warning' : 'default'} /></Link>
        <Link to="/admin/processing"><KpiCard loading={overview.loading} label="Failed Processing" value={o?.failed_processing} hint={o?.notification_failures ? `${o.notification_failures} failed invitations` : ''} icon={o?.failed_processing ? ShieldAlert : AlertTriangle} tone={o?.failed_processing ? 'error' : 'default'} /></Link>
      </div>
      <div className="split">
        <Card title="Audit log" subtitle="Who scheduled, edited, viewed, resent and completed what" flush>
          <DataTable columns={[
            { key: 'when', header: 'When', render: (a) => <span title={formatDateTime(a.timestamp)}>{relativeTime(a.timestamp)}</span> },
            { key: 'user', header: 'User', render: (a) => a.user_name || 'system' },
            { key: 'action', header: 'Action', render: (a) => <span className="mono">{a.action}</span> },
            { key: 'resource', header: 'Resource', render: (a) => (a.resource === 'meeting' && a.resource_id ? <Link className="link" to={`/meetings/${a.resource_id}`}>meeting</Link> : a.resource === 'lead' && a.resource_id ? <Link className="link" to={`/leads/${a.resource_id}`}>lead</Link> : a.resource) },
          ]} rows={activity.data?.items} loading={activity.loading} />
          {activity.data?.total > 0 && <Pagination page={activity.data.page} pageSize={activity.data.page_size} total={activity.data.total} onPage={setPage} />}
        </Card>
        <Card title="Users" actions={<button className="btn btn-sm btn-primary" onClick={() => setCreating(true)}><Plus /> Add user</button>}>
          <div className="list">
            {(users.data || []).map((u) => (
              <div key={u.id} className="list-item" style={{ alignItems: 'center' }}>
                <span className="avatar avatar-sm">{initials(u.name)}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="cell-primary row" style={{ gap: 6 }}>{u.name} {u.is_demo && <DemoBadge />}</div>
                  <div className="cell-secondary">{u.email}{u.last_login_at ? ` · active ${relativeTime(u.last_login_at)}` : ''}</div>
                </div>
                <span className={`badge ${u.role === 'admin' ? 'badge-accent' : ''}`}>{u.role === 'admin' ? 'Admin' : 'Sales'}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
      <CreateUser open={creating} onClose={() => setCreating(false)} onCreated={() => users.refetch({ silent: true })} />
    </div>
  );
}
