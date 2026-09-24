import { NavLink } from 'react-router-dom';
import {
  Activity, CalendarCheck2, LayoutDashboard, ShieldCheck, Users, Webhook,
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';

const MAIN = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/leads', label: 'Leads', icon: Users },
  { to: '/meetings', label: 'Meetings', icon: CalendarCheck2 },
];

const ADMIN = [
  { to: '/admin', label: 'Admin', icon: ShieldCheck, end: true },
  { to: '/admin/webhooks', label: 'Webhook Events', icon: Webhook },
  { to: '/admin/processing', label: 'Processing Monitor', icon: Activity },
];

export function Logo() {
  return (
    <div className="logo">
      <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
        <rect width="32" height="32" rx="8" fill="#15171A" />
        <path d="M9 8.5h5.5a7.5 7.5 0 0 1 0 15H9z" fill="none" stroke="#fff" strokeWidth="2.8" strokeLinejoin="round" />
        <path d="M21 19.5l4.5 4.5M25.5 19.5L21 24" stroke="#EA580C" strokeWidth="2.4" strokeLinecap="round" />
      </svg>
      <span className="logo-text">
        Dora<span className="logo-dot"> X </span>Classify
      </span>
    </div>
  );
}

export function Sidebar({ open, onNavigate }) {
  const { isAdmin } = useAuth();
  const item = (l) => (
    <NavLink key={l.to} to={l.to} end={l.end} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} onClick={onNavigate}>
      <l.icon size={17} aria-hidden="true" />
      <span>{l.label}</span>
    </NavLink>
  );
  return (
    <aside className={`sidebar ${open ? 'open' : ''}`} aria-label="Main navigation">
      <div className="sidebar-brand">
        <Logo />
      </div>
      <nav className="sidebar-nav">
        <div className="nav-section">Workspace</div>
        {MAIN.map(item)}
        {isAdmin && (
          <>
            <div className="nav-section">Administration</div>
            {ADMIN.map(item)}
          </>
        )}
      </nav>
      <div className="sidebar-foot">
        <div className="sidebar-tagline">
          Meeting <span aria-hidden="true">→</span> Intelligence
        </div>
      </div>
    </aside>
  );
}
