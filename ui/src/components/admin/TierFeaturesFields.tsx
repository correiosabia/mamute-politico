import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';

import {
  fetchTierFeatures,
  saveTierFeatures,
  type TierFeatureMode,
} from '@/api/admin';
import { FEATURE_FLAGS, type FeatureFlagKey } from '@/lib/featureFlags';

interface TierFeaturesFieldsProps {
  tierId: number;
  /** Plano fora do ar não aceita edição, como os demais limites. */
  disabled?: boolean;
  onSaved?: () => void;
  onError?: (erro: unknown) => void;
}

const MODOS = [
  { value: 'oculto', label: 'Oculto' },
  { value: 'cadeado', label: 'Cadeado (prévia desfocada)' },
  { value: 'liberado', label: 'Liberado' },
] as const;

/**
 * Modo de cada funcionalidade neste plano (CS-58).
 *
 * O tri-estado global (desativado / só admins / liberado) fica em
 * Configurações gerais e é o ciclo de vida do lançamento. Aqui se decide como
 * cada plano recebe a feature depois que ela saiu da prévia: Oculto (some da
 * tela), Cadeado (entrada visível + prévia desfocada + chamada para assinar)
 * ou Liberado.
 *
 * Plano novo, vindo do sync do Ghost, nasce com tudo oculto.
 *
 * A lista é renderizada a partir do registro do código (`FEATURE_FLAGS`), então
 * flag removida do código some daqui sozinha.
 */
export function TierFeaturesFields({
  tierId,
  disabled = false,
  onSaved,
  onError,
}: TierFeaturesFieldsProps) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'tier-features', tierId],
    queryFn: () => fetchTierFeatures(tierId),
    retry: false,
  });

  const [modos, setModos] = useState<Record<string, TierFeatureMode>>({});
  useEffect(() => {
    if (data) setModos(data.features);
  }, [data]);

  const mutation = useMutation({
    mutationFn: (features: Record<string, TierFeatureMode>) =>
      saveTierFeatures(tierId, features),
    onSuccess: (resultado) => {
      queryClient.setQueryData(['admin', 'tier-features', tierId], resultado);
      // As contagens "liberada/cadeado em N planos" vivem na tela de flags.
      void queryClient.invalidateQueries({
        queryKey: ['admin', 'feature-flags'],
      });
      void queryClient.invalidateQueries({ queryKey: ['feature-flags'] });
      onSaved?.();
    },
    onError: (erro) => onError?.(erro),
  });

  const alterar = (key: string, valor: string) => {
    const proximos = { ...modos };
    if (valor === 'oculto') delete proximos[key];
    else proximos[key] = valor as TierFeatureMode;
    setModos(proximos);
    mutation.mutate(proximos);
  };

  const chaves = Object.keys(FEATURE_FLAGS) as FeatureFlagKey[];

  return (
    <div className="space-y-3">
      <h3 className="text-[12px] font-bold uppercase tracking-wide text-[#383838]/50">
        Funcionalidades
      </h3>

      {isLoading ? (
        <div className="flex items-center gap-2 text-[13px] text-[#383838]/60">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Carregando…
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {chaves.map((key) => (
            <label
              key={key}
              htmlFor={`${tierId}-feature-${key}`}
              className="flex items-center justify-between gap-3 rounded-xl border border-[#383838]/15 px-3 py-2.5"
            >
              <span className="text-[13px] font-semibold text-[#383838]">
                {FEATURE_FLAGS[key].label}
              </span>
              <select
                id={`${tierId}-feature-${key}`}
                value={modos[key] ?? 'oculto'}
                disabled={disabled || mutation.isPending}
                onChange={(e) => alterar(key, e.target.value)}
                className="shrink-0 rounded-full border border-[#383838]/15 px-3 py-1.5 text-[12px] font-semibold text-[#090909]"
              >
                {MODOS.map((op) => (
                  <option key={op.value} value={op.value}>
                    {op.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}

      <p className="text-[11px] text-[#383838]/50">
        Oculto some da tela; Cadeado mostra a entrada com prévia desfocada e
        chamada para assinar; Liberado dá o recurso. Vale só com a
        funcionalidade “liberada” em Configurações gerais. Plano novo nasce
        com tudo oculto.
      </p>
    </div>
  );
}
