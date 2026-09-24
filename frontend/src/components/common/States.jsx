import { AlertTriangle, Inbox, Loader2, RefreshCw } from 'lucide-react';
import { parseError } from '../../services/api';

export function EmptyState({ icon: Icon = Inbox, title, description, action }) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={22} aria-hidden="true" />
      </div>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action && <div style={{ marginTop: 8 }}>{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry, title = 'Could not load this data' }) {
  const e = parseError(error);
  return (
    <div className="empty" role="alert">
      <div className="empty-icon" style={{ background: 'var(--error-bg)', color: 'var(--error)' }}>
        <AlertTriangle size={22} aria-hidden="true" />
      </div>
      <h3>{title}</h3>
      <p>{[e.message, e.reason].filter(Boolean).join(' — ')}</p>
      {onRetry && (
        <button className="btn btn-sm" onClick={() => onRetry()} style={{ marginTop: 8 }}>
          <RefreshCw /> Try again
        </button>
      )}
    </div>
  );
}

export function Spinner({ size = 16, label }) {
  return (
    <span className="row" role="status">
      <Loader2 size={size} className="spin" aria-hidden="true" />
      {label && <span>{label}</span>}
    </span>
  );
}

export function NotAvailable({ children = 'Not available from meeting data' }) {
  return <span className="muted" style={{ fontStyle: 'italic' }}>{children}</span>;
}
