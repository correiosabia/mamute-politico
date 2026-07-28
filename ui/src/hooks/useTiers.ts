import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchTiers,
  syncTiers,
  unarchiveTier,
  updateTier,
  type TierDetails,
} from '@/api/admin';

export function useTiers(includeArchived = false) {
  return useQuery({
    queryKey: ['admin', 'tiers', { includeArchived }],
    queryFn: () => fetchTiers(includeArchived),
  });
}

export function useUpdateTier() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: TierDetails }) =>
      updateTier(id, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'tiers'] }),
  });
}

/** Sincroniza o catálogo do Ghost sob demanda (botão "Sincronizar agora"). */
export function useSyncTiers() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: syncTiers,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'tiers'] }),
  });
}

/** Reativa no Ghost um plano arquivado. O Ghost é a fonte da verdade do status. */
export function useUnarchiveTier() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => unarchiveTier(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'tiers'] }),
  });
}
