import { api, cleanParams } from './api';

export const dashboardApi = {
  overview: (params) => api.get('/api/dashboard/overview', { params: cleanParams(params) }).then((r) => r.data),
  meetings: (params) => api.get('/api/dashboard/meetings', { params: cleanParams(params) }).then((r) => r.data),
  engagement: (params) => api.get('/api/dashboard/engagement', { params: cleanParams(params) }).then((r) => r.data),
  followups: (params) => api.get('/api/dashboard/followups', { params: cleanParams(params) }).then((r) => r.data),
  insights: (params) => api.get('/api/dashboard/insights', { params: cleanParams(params) }).then((r) => r.data),
  search: (q) => api.get('/api/search', { params: { q } }).then((r) => r.data),
};
