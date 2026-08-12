import { useQuery } from '@tanstack/react-query';

import { fetchFeatureFlags } from '@/api/endpoints';
import type { FeatureFlagKey } from '@/lib/featureFlags';

/**
 * Estado da feature flag para o usuário atual.
 *
 * O backend já resolve o tri-estado (`off`/`admins`/`all`) e devolve booleano,
 * então aqui não há regra a repetir — e o call site fica com o menor formato
 * possível, que é o que torna a remoção da flag barata.
 *
 * Uma única query compartilhada: N chamadas do hook na mesma tela não viram N
 * requests. Enquanto carrega devolve `false` — é preferível a feature aparecer
 * só depois de resolver a piscar na tela de quem não deveria vê-la. Falha de
 * rede também vale `false`, pelo mesmo motivo.
 *
 * Para remover a flag, veja o procedimento em `@/lib/featureFlags`.
 */
export function useFeatureFlag(key: FeatureFlagKey): boolean {
  const { data } = useQuery({
    queryKey: ['feature-flags'],
    queryFn: fetchFeatureFlags,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  return data?.[key] === true;
}
