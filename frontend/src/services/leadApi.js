import { api, cleanParams, downloadFile } from './api';

export const leadApi = {
  list: (params) => api.get('/api/leads', { params: cleanParams(params) }).then((r) => r.data),
  get: (id) => api.get(`/api/leads/${id}`).then((r) => r.data),
  create: (body) => api.post('/api/leads', body).then((r) => r.data),
  update: (id, body) => api.put(`/api/leads/${id}`, body).then((r) => r.data),
  remove: (id) => api.delete(`/api/leads/${id}`),
  analytics: (id) => api.get(`/api/leads/${id}/analytics`).then((r) => r.data),
  meetings: (id) => api.get(`/api/leads/${id}/meetings`).then((r) => r.data),
  exportCsv: (params) => downloadFile('/api/leads/export.csv', cleanParams(params), 'leads.csv'),
  salesPeople: () => api.get('/api/users/sales-people').then((r) => r.data),
};
