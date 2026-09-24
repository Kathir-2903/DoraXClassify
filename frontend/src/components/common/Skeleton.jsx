export function Skeleton({ width = '100%', height = 14, radius, style }) {
  return <div className="skeleton" style={{ width, height, borderRadius: radius, ...style }} aria-hidden="true" />;
}

export function SkeletonCard({ lines = 3, height = 120 }) {
  return (
    <div className="card card-body" aria-busy="true" aria-label="Loading">
      <Skeleton width="40%" height={14} />
      <div style={{ height: 12 }} />
      {lines > 0 ? (
        Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} width={`${90 - i * 12}%`} height={11} style={{ marginBottom: 9 }} />
        ))
      ) : (
        <Skeleton height={height} />
      )}
    </div>
  );
}

export function SkeletonTable({ rows = 6, cols = 6 }) {
  return (
    <div style={{ padding: 14 }} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 16, padding: '10px 0' }}>
          {Array.from({ length: cols }).map((__, c) => (
            <Skeleton key={c} height={11} width={c === 0 ? '80%' : '60%'} />
          ))}
        </div>
      ))}
    </div>
  );
}
