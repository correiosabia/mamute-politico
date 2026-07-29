import { useQuery } from '@tanstack/react-query';
import {
  fetchEmails,
  fetchCredits,
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

export function useCredits() {
  return useQuery({
    queryKey: ['admin', 'metrics', 'credits'],
    queryFn: fetchCredits,
    // Saldo muda a cada consulta do chat; sem refetch o painel mostraria valor
    // velho justamente quando ele importa.
    refetchInterval: 60_000,
    retry: false,
  });
}

export function useEmails() {
  return useQuery({ queryKey: ['admin', 'metrics', 'emails'], queryFn: fetchEmails });
}
