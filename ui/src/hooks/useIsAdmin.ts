import { useQuery } from '@tanstack/react-query';
import { fetchWhoami } from '@/api/admin';
import { useGhostAuth } from '@/components/auth/ghost-auth/react/useGhostAuth';

/** Deriva status de admin do backend. 404/erro => não admin. */
export function useIsAdmin(): { isAdmin: boolean; isLoading: boolean } {
  const token = useGhostAuth();
  const query = useQuery({
    queryKey: ['admin', 'whoami'],
    queryFn: fetchWhoami,
    enabled: Boolean(token),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  return {
    isAdmin: query.data?.is_admin === true,
    isLoading: Boolean(token) && query.isLoading,
  };
}
