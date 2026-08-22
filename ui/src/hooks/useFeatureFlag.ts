import { useQuery } from '@tanstack/react-query';

import { fetchFeatureFlags } from '@/api/endpoints';
import { useGhostAuth } from '@/components/auth/ghost-auth/react/useGhostAuth';
import type { FeatureFlagKey } from '@/lib/featureFlags';

/**
 * Uma única definição da query, compartilhada pelos dois hooks abaixo: se cada
 * um trouxesse a sua, `staleTime`/`retry` divergiriam com o tempo.
 *
 * O token entra na chave por um motivo concreto: se ele estiver expirado no
 * boot, a rota devolve 401 e — com `retry: false` — a query fica em erro, o que
 * faz TODA flag ler `false` e a interface aparecer sem as features liberadas.
 * O serviço de auth renova o token em seguida; com ele na chave, a renovação
 * troca a chave e refaz a busca sozinha. Invalidação por prefixo
 * (`['feature-flags']`, usada no painel de flags) continua alcançando.
 */
function useFeatureFlagsQuery() {
  const token = useGhostAuth();

  return useQuery({
    queryKey: ['feature-flags', token],
    queryFn: fetchFeatureFlags,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

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
  const { data } = useFeatureFlagsQuery();

  return data?.[key] === 'liberada';
}

/**
 * Mesma resolução do `useFeatureFlag`, com o carregamento exposto.
 *
 * Existe só para portão de ROTA, que precisa distinguir "ainda não sei" de
 * "não pode": redirecionar enquanto carrega expulsaria justamente quem tem
 * acesso, porque `liberada` só é conhecida depois da resposta. Portão dentro
 * de tela não precisa disto — lá omitir por um instante é inofensivo, e é o
 * comportamento desejado.
 *
 * Mesma forma do `useIsAdmin`, que o `RequireAdmin` já consome em App.tsx.
 */
export function useFeatureFlagStatus(key: FeatureFlagKey): {
  liberada: boolean;
  isLoading: boolean;
} {
  const { data, isLoading } = useFeatureFlagsQuery();

  return { liberada: data?.[key] === 'liberada', isLoading };
}
