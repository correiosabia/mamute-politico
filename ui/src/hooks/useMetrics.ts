import { useQuery } from '@tanstack/react-query';
import {
  fetchEmails,
  fetchIa,
  fetchMetricsOverview,
  fetchMetricsUsers,
  fetchParliamentarians,
  fetchSections,
  fetchTools,
  fetchUserDetail,
} from '@/api/admin';

export function useMetricsOverview() {
  return useQuery({
    queryKey: ['admin', 'metrics', 'overview'],
    queryFn: fetchMetricsOverview,
  });
}

export function useMetricsUsers(params?: { limit?: number; search?: string }) {
  return useQuery({
    queryKey: ['admin', 'metrics', 'users', params ?? {}],
    queryFn: () => fetchMetricsUsers(params),
  });
}

export function useUserDetail(id: number) {
  return useQuery({
    queryKey: ['admin', 'metrics', 'users', id],
    queryFn: () => fetchUserDetail(id),
    enabled: Number.isFinite(id),
  });
}

export function useTools() {
  return useQuery({ queryKey: ['admin', 'metrics', 'tools'], queryFn: fetchTools });
}

export function useSections() {
  return useQuery({ queryKey: ['admin', 'metrics', 'sections'], queryFn: fetchSections });
}

export function useParliamentarians() {
  return useQuery({
    queryKey: ['admin', 'metrics', 'parliamentarians'],
    queryFn: fetchParliamentarians,
  });
}

export function useIa() {
  return useQuery({ queryKey: ['admin', 'metrics', 'ia'], queryFn: fetchIa });
}

export function useEmails() {
  return useQuery({ queryKey: ['admin', 'metrics', 'emails'], queryFn: fetchEmails });
}
