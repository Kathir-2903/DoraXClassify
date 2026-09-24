import { api, cleanParams } from './api';

export const analyticsApi = {
  settings: () => api.get('/api/settings').then((r) => r.data),
};

export const adminApi = {
  overview: () => api.get('/api/admin/overview').then((r) => r.data),
  webhooks: (params) => api.get('/api/admin/webhooks', { params: cleanParams(params) }).then((r) => r.data),
  reprocessWebhook: (id) => api.post(`/api/admin/webhooks/${id}/reprocess`).then((r) => r.data),
  processing: (params) => api.get('/api/admin/processing', { params: cleanParams(params) }).then((r) => r.data),
  retry: (meetingId, stage) => api.post(`/api/admin/processing/${meetingId}/retry`, null, { params: { stage } }).then((r) => r.data),
  users: () => api.get('/api/admin/users').then((r) => r.data),
  createUser: (body) => api.post('/api/admin/users', body).then((r) => r.data),
  activity: (params) => api.get('/api/admin/activity', { params: cleanParams(params) }).then((r) => r.data),
};
