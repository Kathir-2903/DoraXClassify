import { useState } from 'react';
import { BarChart3, Table2 } from 'lucide-react';
import { Card } from '../cards/Card';
import { AIBadge } from '../badges/Badge';
import { SkeletonCard } from '../common/Skeleton';
import { EmptyState } from '../common/States';

/** Card wrapper that always offers an accessible table view of the data. */
export function ChartCard({ title, subtitle, ai, loading, empty, emptyText, table, children, height = 260, actions }) {
  const [view, setView] = useState('chart');
  if (loading) return <SkeletonCard lines={0} height={height} />;
  const toggle = table ? (
    <div className="chip-tabs" role="tablist" aria-label="Chart view">
      <button className={`chip-tab ${view === 'chart' ? 'active' : ''}`} onClick={() => setView('chart')} aria-label="Chart view" role="tab" aria-selected={view === 'chart'}>
        <BarChart3 size={13} />
      </button>
      <button className={`chip-tab ${view === 'table' ? 'active' : ''}`} onClick={() => setView('table')} aria-label="Table view" role="tab" aria-selected={view === 'table'}>
        <Table2 size={13} />
      </button>
    </div>
  ) : null;
  return (
    <Card title={title} subtitle={subtitle} badge={ai ? <AIBadge /> : null} actions={<>{actions}{toggle}</>}>
      {empty ? (
        <EmptyState title="Not enough data yet" description={emptyText || 'This chart fills in as meetings are completed.'} />
      ) : view === 'table' && table ? (
        <div className="table-wrap" style={{ maxHeight: height, overflowY: 'auto' }}>
          <table className="table">
            <thead>
              <tr>{table.columns.map((c) => <th key={c}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {table.rows.map((r, i) => (
                <tr key={i}>{r.map((v, j) => <td key={j} className="tabular">{v}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ height }}>{children}</div>
      )}
    </Card>
  );
}

export function Legend({ items }) {
  return (
    <ul className="chart-legend" aria-label="Legend">
      {items.map((it) => (
        <li key={it.label}>
          <span className="swatch" style={{ background: it.color }} aria-hidden="true" />
          <span>{it.label}</span>
          {it.value !== undefined && <strong className="tabular">{it.value}</strong>}
        </li>
      ))}
    </ul>
  );
}

export function ChartTooltip({ active, payload, label, labelFormatter, valueFormatter = (v) => v }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      {label !== undefined && <div className="chart-tooltip-label">{labelFormatter ? labelFormatter(label) : label}</div>}
      {payload.map((p) => (
        <div key={p.dataKey || p.name} className="chart-tooltip-row">
          <span className="swatch" style={{ background: p.color || p.payload?.fill }} aria-hidden="true" />
          <span>{p.name}</span>
          <strong className="tabular">{valueFormatter(p.value, p)}</strong>
        </div>
      ))}
    </div>
  );
}
