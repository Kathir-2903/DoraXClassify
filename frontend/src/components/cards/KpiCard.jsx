import { memo } from 'react';
import { Skeleton } from '../common/Skeleton';
import { AIBadge } from '../badges/Badge';

function KpiCardBase({ label, value, hint, icon: Icon, tone = 'default', loading, ai, onClick }) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag className={`kpi-card kpi-${tone} ${onClick ? 'kpi-clickable' : ''}`} onClick={onClick}>
      <div className="kpi-top">
        <span className="kpi-label">{label}</span>
        {Icon && (
          <span className="kpi-icon" aria-hidden="true">
            <Icon size={15} />
          </span>
        )}
      </div>
      {loading ? (
        <Skeleton width="55%" height={26} style={{ margin: '6px 0 4px' }} />
      ) : (
        <div className="kpi-value">{value ?? '—'}</div>
      )}
      <div className="kpi-hint">
        {ai && <AIBadge label="AI" />}
        {hint}
      </div>
    </Tag>
  );
}

export const KpiCard = memo(KpiCardBase);
