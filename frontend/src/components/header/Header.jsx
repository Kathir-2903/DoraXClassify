import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CalendarCheck2, FlaskConical, LogOut, Menu, Search } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { useDebounce } from '../../hooks/useDebounce';
import { useSettings } from '../../hooks/useAnalytics';
import { dashboardApi } from '../../services/dashboardApi';
import { initials } from '../../utils/formatting';
import { formatDateTime } from '../../utils/date';
import { StatusBadge } from '../badges/Badge';

function GlobalSearch() {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState(null);
  const [active, setActive] = useState(0);
  const debounced = useDebounce(q, 250);
  const navigate = useNavigate();
  const boxRef = useRef(null);

  useEffect(() => {
    if (debounced.trim().length < 2) {
      setResults(null);
      return;
    }
    let cancelled = false;
    dashboardApi.search(debounced.trim()).then((r) => !cancelled && setResults(r)).catch(() => !cancelled && setResults({ leads: [], meetings: [] }));
    return () => {
      cancelled = true;
    };
  }, [debounced]);

  useEffect(() => {
    const onDoc = (e) => !boxRef.current?.contains(e.target) && setOpen(false);
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        boxRef.current?.querySelector('input')?.focus();
      }
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, []);

  const items = results
    ? [
        ...results.leads.map((l) => ({ kind: 'lead', id: l.id, title: l.name, sub: [l.email, l.company].filter(Boolean).join(' · '), to: `/leads/${l.id}` })),
        ...results.meetings.map((m) => ({ kind: 'meeting', id: m.id, title: m.label, sub: `${m.lead_snapshot?.name} · ${formatDateTime(m.schedule?.start_time)}`, to: `/meetings/${m.id}`, state: m.status?.overall })),
      ]
    : [];

  const go = (item) => {
    navigate(item.to);
    setOpen(false);
    setQ('');
  };

  return (
    <div className="global-search" ref={boxRef}>
      <div className="input-icon">
        <Search aria-hidden="true" />
        <input
          className="input"
          placeholder="Search leads, emails, phones, meetings…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
            setActive(0);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') setActive((a) => Math.min(a + 1, items.length - 1));
            if (e.key === 'ArrowUp') setActive((a) => Math.max(a - 1, 0));
            if (e.key === 'Enter' && items[active]) go(items[active]);
            if (e.key === 'Escape') setOpen(false);
          }}
          aria-label="Global search"
          role="combobox"
          aria-expanded={open && Boolean(results)}
          aria-controls="search-results"
        />
        <kbd className="kbd">⌘K</kbd>
      </div>
      {open && results && (
        <div className="search-pop" id="search-results" role="listbox">
          {items.length === 0 && <div className="search-empty">No results for “{debounced}”</div>}
          {results.leads.length > 0 && <div className="search-group">Leads</div>}
          {items.map((it, i) => (
            <div key={`${it.kind}-${it.id}`}>
              {it.kind === 'meeting' && i === results.leads.length && <div className="search-group">Meetings</div>}
              <button className={`search-item ${i === active ? 'active' : ''}`} onClick={() => go(it)} role="option" aria-selected={i === active}>
                <span className="avatar avatar-sm">{it.kind === 'lead' ? initials(it.title) : <CalendarCheck2 size={13} />}</span>
                <span className="search-text">
                  <span className="cell-primary">{it.title}</span>
                  <span className="cell-secondary">{it.sub}</span>
                </span>
                {it.state && <StatusBadge state={it.state} />}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Header({ onMenu }) {
  const { user, logout } = useAuth();
  const { data: settings } = useSettings();
  const [menu, setMenu] = useState(false);
  const mock = settings?.integrations?.classify?.mock_mode;
  return (
    <header className="topbar">
      <button className="btn btn-ghost btn-icon menu-btn" onClick={onMenu} aria-label="Open navigation">
        <Menu />
      </button>
      <GlobalSearch />
      <div className="topbar-right">
        {mock && (
          <span className="badge badge-accent" title="Classify, Gemini and email integrations run in mock mode">
            <FlaskConical size={12} /> Demo mode
          </span>
        )}
        <div className="user-menu">
          <button className="user-btn" onClick={() => setMenu((m) => !m)} aria-haspopup="menu" aria-expanded={menu}>
            <span className="avatar avatar-sm">{initials(user?.name)}</span>
            <span className="user-meta">
              <span className="cell-primary">{user?.name}</span>
              <span className="cell-secondary">{user?.role === 'admin' ? 'Administrator' : 'Sales'}</span>
            </span>
          </button>
          {menu && (
            <div className="menu-pop" role="menu" onMouseLeave={() => setMenu(false)}>
              <button role="menuitem" onClick={logout}>
                <LogOut size={14} /> Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
