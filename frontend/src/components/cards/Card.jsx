export function Card({ title, subtitle, actions, children, flush = false, className = '', icon: Icon, badge }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-header">
          <div style={{ minWidth: 0 }}>
            <h2 className="card-title">
              {Icon && <Icon size={16} aria-hidden="true" style={{ color: 'var(--text-3)' }} />}
              {title}
              {badge}
            </h2>
            {subtitle && <p className="card-subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </header>
      )}
      <div className={`card-body ${flush ? 'flush' : ''}`}>{children}</div>
    </section>
  );
}
