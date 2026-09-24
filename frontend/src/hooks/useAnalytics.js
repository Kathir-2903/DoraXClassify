import { analyticsApi } from '../services/analyticsApi';
import { dashboardApi } from '../services/dashboardApi';
import { useAsync } from './useAsync';

export function useDashboard(salesPersonId) {
  const params = { sales_person_id: salesPersonId };
  const k = salesPersonId || 'all';
  return {
    overview: useAsync(() => dashboardApi.overview(params), [k], { key: `dash-overview:${k}` }),
    meetings: useAsync(() => dashboardApi.meetings({ ...params, days: 30 }), [k], { key: `dash-meetings:${k}` }),
    engagement: useAsync(() => dashboardApi.engagement(params), [k], { key: `dash-engagement:${k}` }),
    followups: useAsync(() => dashboardApi.followups(params), [k], { key: `dash-followups:${k}` }),
    insights: useAsync(() => dashboardApi.insights(params), [k], { key: `dash-insights:${k}` }),
  };
}

export function useSettings() {
  return useAsync(() => analyticsApi.settings(), [], { key: 'settings', ttl: 60000 });
}
