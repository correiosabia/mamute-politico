import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchTiers, updateTier, type TierDetails } from '@/api/admin';

export function useTiers() {
  return useQuery({ queryKey: ['admin', 'tiers'], queryFn: fetchTiers });
}

export function useUpdateTier() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: TierDetails }) =>
      updateTier(id, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'tiers'] }),
  });
}
