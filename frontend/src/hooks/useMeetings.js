import { meetingApi } from '../services/meetingApi';
import { useAsync } from './useAsync';

export function useMeetings(params) {
  const key = `meetings:${JSON.stringify(params)}`;
  return useAsync(() => meetingApi.list(params), [key], { key, ttl: 10000 });
}

export function useMeeting(id) {
  return useAsync(() => meetingApi.get(id), [id]);
}
