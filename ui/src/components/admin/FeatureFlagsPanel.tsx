import { useSyncExternalStore } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Eye, EyeOff, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { fetchFeatureFlagsAdmin, saveFeatureFlag } from '@/api/admin';
import {
  FEATURE_FLAGS,
  FLAG_AGE_WARNING_DAYS,
  flagAgeInDays,
  type FeatureFlagKey,
} from '@/lib/featureFlags';
import {
  getPreviewKeys,
  subscribeFeaturePreview,
  toggleFeaturePreview,
} from '@/lib/featurePreview';

const ESTADOS = [
  { value: 'off', label: 'Desativado' },
  { value: 'admins', label: 'Só para admins' },
  { value: 'all', label: 'Liberado (vale o plano)' },
] as const;

export function FeatureFlagsPanel() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'feature-flags'],
    queryFn: fetchFeatureFlagsAdmin,
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: ({ key, state }: { key: string; state: string }) =>
      saveFeatureFlag(key, state),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ['admin', 'feature-flags'],
      });
      // O app lê a versão resolvida; invalidar evita o usuário ver o estado velho.
      void queryClient.invalidateQueries({ queryKey: ['feature-flags'] });
      toast.success('Funcionalidade atualizada.');
    },
    onError: () => toast.error('Não foi possível salvar. Tente novamente.'),
  });

  // Itera sobre o REGISTRO do código, nunca sobre a resposta do banco: é isso
  // que faz uma flag removida do código sumir deste controle sozinha, sem
  // precisar de um segundo mecanismo para esconder o botão.
  const doBanco = new Map((data ?? []).map((f) => [f.key, f]));
  const chaves = Object.keys(FEATURE_FLAGS) as FeatureFlagKey[];
  // Preview "ver como bloqueada" (CS-58): lente por admin e por navegador.
  const previewKeys = useSyncExternalStore(
    subscribeFeaturePreview,
    getPreviewKeys,
    getPreviewKeys
  );

  return (
    <section aria-label="Funcionalidades" className="flex flex-col gap-4">
      <div>
        <h2 className="text-[24px] font-bold leading-none text-[#090909]">
          Funcionalidades
        </h2>
        <p className="mt-1 text-[14px] text-[#383838]/70">
          Valem na hora, sem redeploy. Controlam a exibição na interface — os
          dados seguem disponíveis na API.
        </p>
      </div>

      {isLoading ? (
        <div className="mp-card flex items-center gap-2 bg-white p-6 text-[#383838]/60">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
          Carregando…
        </div>
      ) : (
        <div className="mp-card flex flex-col divide-y divide-[#383838]/10 bg-white">
          {chaves.map((key) => {
            const { label, since } = FEATURE_FLAGS[key];
            const linha = doBanco.get(key);
            const estado = linha?.state ?? 'off';
            const idade = flagAgeInDays(since);
            const velha = idade > FLAG_AGE_WARNING_DAYS;
            const liberados = linha?.tiers_liberados ?? 0;
            const cadeados = linha?.tiers_cadeado ?? 0;
            // Flag liberada sem nenhum plano não aparece para ninguém. É o
            // erro silencioso do desenho — melhor gritar aqui.
            const semPlano = estado === 'all' && liberados + cadeados === 0;
            const previewOn = previewKeys.includes(key);

            return (
              <div
                key={key}
                className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="space-y-0.5">
                  <label
                    htmlFor={`ff-${key}`}
                    className="text-[15px] font-semibold text-[#090909]"
                  >
                    {label}
                  </label>
                  <p
                    className={
                      velha
                        ? 'text-[12px] font-semibold text-[#b45309]'
                        : 'text-[12px] text-[#383838]/60'
                    }
                  >
                    criada há {idade} dias
                    {velha ? ' — candidata a remoção do código' : ''}
                  </p>
                  {estado === 'all' && (
                    <p
                      className={
                        semPlano
                          ? 'text-[12px] font-semibold text-[#b45309]'
                          : 'text-[12px] text-[#383838]/60'
                      }
                    >
                      {semPlano
                        ? 'Nenhum plano libera esta funcionalidade — ninguém a vê. Configure em Planos.'
                        : `Liberada em ${liberados} de ${linha?.tiers_total} planos` +
                          (cadeados > 0
                            ? `, com cadeado em ${cadeados}.`
                            : '.')}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {/* Preview só-admin: renderiza ESTA feature como bloqueada
                      (cadeado + blur + CTA) e manda o header que o backend
                      honra apenas para admin — simulação de ponta a ponta,
                      sem tocar estado nem plano nenhum. */}
                  <button
                    type="button"
                    onClick={() => toggleFeaturePreview(key)}
                    title={
                      previewOn
                        ? 'Deixar de ver como bloqueada'
                        : 'Ver como bloqueada (só afeta você, neste navegador)'
                    }
                    aria-pressed={previewOn}
                    className={`rounded-full border p-2 transition ${
                      previewOn
                        ? 'border-[#b45309] bg-amber-50 text-[#b45309]'
                        : 'border-[#383838]/15 text-[#383838]/70'
                    }`}
                  >
                    {previewOn ? (
                      <EyeOff className="h-4 w-4" aria-hidden />
                    ) : (
                      <Eye className="h-4 w-4" aria-hidden />
                    )}
                  </button>
                  <select
                    id={`ff-${key}`}
                    value={estado}
                    disabled={mutation.isPending}
                    onChange={(e) =>
                      mutation.mutate({ key, state: e.target.value })
                    }
                    className="rounded-full border border-[#383838]/15 px-4 py-2 text-[13px] font-semibold text-[#090909]"
                  >
                    {ESTADOS.map((op) => (
                      <option key={op.value} value={op.value}>
                        {op.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
