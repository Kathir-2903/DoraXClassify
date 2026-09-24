import { api, cleanParams, downloadFile } from './api';

export const meetingApi = {
  schedule: (body, idempotencyKey) =>
    api.post('/api/meetings/schedule', body, { headers: { 'Idempotency-Key': idempotencyKey }, timeout: 60000 }).then((r) => r.data),
  list: (params) => api.get('/api/meetings', { params: cleanParams(params) }).then((r) => r.data),
  get: (id) => api.get(`/api/meetings/${id}`).then((r) => r.data),
  status: (id) => api.get(`/api/meetings/${id}/status`).then((r) => r.data),
  resendEmail: (id) => api.post(`/api/meetings/${id}/send-email`).then((r) => r.data),
  transcript: (id, q) => api.get(`/api/meetings/${id}/transcript`, { params: cleanParams({ q }) }).then((r) => r.data),
  analysis: (id, versionId) => api.get(`/api/meetings/${id}/analysis`, { params: cleanParams({ version_id: versionId }) }).then((r) => r.data),
  reanalyze: (id, reason) => api.post(`/api/meetings/${id}/reanalyze`, { reason }, { timeout: 180000 }).then((r) => r.data),
  retry: (id, stage) => api.post(`/api/meetings/${id}/retry`, null, { params: { stage } }).then((r) => r.data),
  recording: (id) => api.get(`/api/meetings/${id}/recording`).then((r) => r.data),
  simulate: (id, body) => api.post(`/api/meetings/${id}/simulate`, body).then((r) => r.data),
  syncAttendance: (id) => api.post(`/api/meetings/${id}/sync-attendance`, null, { timeout: 60000 }).then((r) => r.data),
  exportCsv: (params) => downloadFile('/api/meetings/export.csv', cleanParams(params), 'meetings.csv'),
  downloadTranscript: (id) => downloadFile(`/api/meetings/${id}/transcript/download`, {}, 'transcript.txt'),
  downloadReport: (id) => downloadFile(`/api/meetings/${id}/report.pdf`, {}, 'meeting-report.pdf'),
};
