import { leadApi } from '../services/leadApi';
import { useAsync } from './useAsync';

export function useLeads(params) {
  const key = `leads:${JSON.stringify(params)}`;
  return useAsync(() => leadApi.list(params), [key], { key, ttl: 15000 });
}

export function useLead(id) {
  return useAsync(() => leadApi.get(id), [id], { key: `lead:${id}`, ttl: 5000 });
}

export function useLeadAnalytics(id) {
  return useAsync(() => leadApi.analytics(id), [id], { key: `lead-analytics:${id}`, ttl: 5000 });
}

export function useSalesPeople() {
  return useAsync(() => leadApi.salesPeople(), [], { key: 'sales-people', ttl: 300000 });
}
