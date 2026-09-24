import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import { SkeletonTable } from '../common/Skeleton';

/**
 * columns: [{ key, header, render(row), sortKey, sticky, className, width }]
 * sort: { key, order } ; onSort(key)
 */
export function DataTable({ columns, rows, loading, empty, onRowClick, sort, onSort, rowKey = (r) => r.id, caption }) {
  if (loading && !rows?.length) return <SkeletonTable cols={Math.min(columns.length, 7)} />;
  if (!rows?.length) return empty || null;
  return (
    <div className="table-wrap" style={{ opacity: loading ? 0.6 : 1, transition: 'opacity .15s' }}>
      <table className="table responsive">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((col) => {
              const active = Boolean(col.sortKey) && sort?.key === col.sortKey;
              const Icon = active ? (sort.order === 'asc' ? ArrowUp : ArrowDown) : ArrowUpDown;
              return (
                <th
                  key={col.key}
                  className={`${col.sortKey ? 'sortable' : ''} ${col.sticky ? 'sticky-col' : ''} ${col.stickyRight ? 'sticky-right' : ''}`}
                  style={{ width: col.width }}
                  onClick={col.sortKey && onSort ? () => onSort(col.sortKey) : undefined}
                  aria-sort={active ? (sort.order === 'asc' ? 'ascending' : 'descending') : undefined}
                  scope="col"
                >
                  <span className="row" style={{ gap: 4 }}>
                    {col.header}
                    {col.sortKey && <Icon size={12} style={{ opacity: active ? 1 : 0.4 }} aria-hidden="true" />}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className={onRowClick ? 'clickable' : ''}
              onClick={onRowClick ? (e) => !e.target.closest('button, a, input, select') && onRowClick(row) : undefined}
            >
              {columns.map((col) => (
                <td key={col.key} data-label={col.mobileLabel ?? (typeof col.header === 'string' ? col.header : '')}
                    className={`${col.sticky ? 'sticky-col' : ''} ${col.stickyRight ? 'sticky-right' : ''} ${col.className || ''}`}>
                  {col.render ? col.render(row) : row[col.key] ?? '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total ? (page - 1) * pageSize + 1 : 0;
  const to = Math.min(total, page * pageSize);
  return (
    <div className="pagination">
      <span className="tabular">
        {from}–{to} of {total}
      </span>
      <div className="row">
        <button className="btn btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Previous
        </button>
        <span className="tabular">
          Page {page} of {pages}
        </span>
        <button className="btn btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next
        </button>
      </div>
    </div>
  );
}
