import { useSyncExternalStore } from 'react';
import { useQuery } from '@tanstack/react-query';

import { fetchFeatureFlags } from '@/api/endpoints';
import { useGhostAuth } from '@/components/auth/ghost-auth/react/useGhostAuth';
import {
  isFeaturePreviewOn,
  subscribeFeaturePreview,
} from '@/lib/featurePreview';
import type { FeatureFlagKey } from '@/lib/featureFlags';

export type FeatureAccessValue = 'liberada' | 'bloqueada' | 'oculta';

/**
 * Acesso resolvido do usuário a uma feature, nos três valores da CS-58.
 *
 * `useFeatureFlag` continua sendo o portão comum (booleano). Este hook é só
 * para os pontos de montagem que sabem renderizar o estado 'bloqueada'
 * (cadeado + prévia desfocada). Carregando/erro/chave ausente valem
 * 'oculta' — o mais restritivo, como no hook booleano.
 *
 * O preview de admin ("ver como bloqueada", em /admin/configuracoes) degrada
 * SÓ 'liberada' → 'bloqueada': simular nunca revela o que está oculto.
 */
export function useFeatureAccess(key: FeatureFlagKey): FeatureAccessValue {
  const token = useGhostAuth();

  const { data } = useQuery({
    queryKey: ['feature-flags', token],
    queryFn: fetchFeatureFlags,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const previewOn = useSyncExternalStore(
    subscribeFeaturePreview,
    () => isFeaturePreviewOn(key),
    () => false
  );

  const value = data?.[key];
  if (value === 'liberada') return previewOn ? 'bloqueada' : 'liberada';
  if (value === 'bloqueada') return 'bloqueada';
  return 'oculta';
}
