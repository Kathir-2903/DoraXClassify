import { lazy } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { AppLayout, PageFallback } from '../components/layout/AppLayout';

const Login = lazy(() => import('../pages/Login/Login'));
const Dashboard = lazy(() => import('../pages/Dashboard/Dashboard'));
const Leads = lazy(() => import('../pages/Leads/Leads'));
const LeadDetails = lazy(() => import('../pages/LeadDetails/LeadDetails'));
const Meetings = lazy(() => import('../pages/Meetings/Meetings'));
const MeetingDetails = lazy(() => import('../pages/MeetingDetails/MeetingDetails'));
const AdminOverview = lazy(() => import('../pages/Admin/AdminOverview'));
const AdminWebhooks = lazy(() => import('../pages/Admin/AdminWebhooks'));
const AdminProcessing = lazy(() => import('../pages/Admin/AdminProcessing'));
const DemoMeeting = lazy(() => import('../pages/DemoMeeting/DemoMeeting'));
const NotFound = lazy(() => import('../pages/NotFound/NotFound'));

function RequireAuth({ children, admin = false }) {
  const { user, loading, isAdmin } = useAuth();
  const location = useLocation();
  if (loading) return <PageFallback />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (admin && !isAdmin) return <Navigate to="/dashboard" replace />;
  return children;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/demo/meeting/:uniqueId" element={<DemoMeeting />} />
      <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/leads" element={<Leads />} />
        <Route path="/leads/:leadId" element={<LeadDetails />} />
        <Route path="/meetings" element={<Meetings />} />
        <Route path="/meetings/:meetingId" element={<MeetingDetails />} />
        <Route path="/admin" element={<RequireAuth admin><AdminOverview /></RequireAuth>} />
        <Route path="/admin/webhooks" element={<RequireAuth admin><AdminWebhooks /></RequireAuth>} />
        <Route path="/admin/processing" element={<RequireAuth admin><AdminProcessing /></RequireAuth>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
