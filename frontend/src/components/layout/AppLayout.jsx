import { Suspense, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from '../sidebar/Sidebar';
import { Header } from '../header/Header';
import { SkeletonCard } from '../common/Skeleton';

export function PageFallback() {
  return (
    <div className="page">
      <div className="kpi-grid" style={{ marginBottom: 16 }}>
        {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} lines={1} />)}
      </div>
      <SkeletonCard lines={0} height={280} />
    </div>
  );
}

export function AppLayout() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  return (
    <div className="shell">
      <Sidebar open={open} onNavigate={() => setOpen(false)} />
      {open && <div className="scrim" onClick={() => setOpen(false)} aria-hidden="true" />}
      <div className="main">
        <Header onMenu={() => setOpen(true)} />
        <main id="content">
          <Suspense fallback={<PageFallback />} key={location.pathname}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
