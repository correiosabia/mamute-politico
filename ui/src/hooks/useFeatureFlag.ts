import { useQuery } from '@tanstack/react-query';

import { fetchFeatureFlags } from '@/api/endpoints';
import { useGhostAuth } from '@/components/auth/ghost-auth/react/useGhostAuth';
import type { FeatureFlagKey } from '@/lib/featureFlags';

/**
 * Estado da feature flag para o usuário atual, como booleano.
 *
 * O backend já resolve tri-estado + modo do plano e devolve
 * `'liberada' | 'bloqueada' | 'oculta'`; aqui só 'liberada' vale `true` —
 * cadeado é vitrine, não acesso. Pontos de montagem que sabem renderizar o
 * estado 'bloqueada' usam `useFeatureAccess`.
 *
 * Uma única query compartilhada: N chamadas do hook na mesma tela não viram N
 * requests. Enquanto carrega devolve `false` — é preferível a feature aparecer
 * só depois de resolver a piscar na tela de quem não deveria vê-la. Falha de
 * rede também vale `false`, pelo mesmo motivo.
 *
 * Para remover a flag, veja o procedimento em `@/lib/featureFlags`.
 */
export function useFeatureFlag(key: FeatureFlagKey): boolean {
  const token = useGhostAuth();
  // O token entra na chave porque, se ele estiver expirado no boot, a rota
  // devolve 401 e — com `retry: false` — a query fica em erro, fazendo TODA
  // flag ler `false` (interface sem as features liberadas). O serviço de auth
  // renova o token em seguida; com ele na chave, a renovação refaz a busca.
  // ATENÇÃO: esta query é a MESMA de `useFeatureAccess.ts`. Mexeu aqui, mexa lá.
  const { data } = useQuery({
    queryKey: ['feature-flags', token],
    queryFn: fetchFeatureFlags,
    staleTime: 5 * 60 * 1000,
    retry: false,
    enabled: Boolean(token),
  });

  return data?.[key] === 'liberada';
}

