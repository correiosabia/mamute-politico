import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';

import { fetchTierFeatures, saveTierFeatures } from '@/api/admin';
import { FEATURE_FLAGS, type FeatureFlagKey } from '@/lib/featureFlags';

interface TierFeaturesFieldsProps {
  tierId: number;
  /** Plano fora do ar não aceita edição, como os demais limites. */
  disabled?: boolean;
  onSaved?: () => void;
  onError?: (erro: unknown) => void;
}

/**
 * Quais funcionalidades este plano libera.
 *
 * O tri-estado global (desativado / só admins / liberado) fica em
 * Configurações gerais e é o ciclo de vida do lançamento. Aqui se decide quem
 * recebe depois que a feature saiu da prévia — por isso "liberado" lá não
 * significa "todo mundo vê", e sim "agora quem decide é o plano".
 *
 * Plano novo, vindo do sync do Ghost, nasce sem nenhuma marcada.
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

  const [marcadas, setMarcadas] = useState<string[]>([]);
  useEffect(() => {
    if (data) setMarcadas(data.features);
  }, [data]);

  const mutation = useMutation({
    mutationFn: (features: string[]) => saveTierFeatures(tierId, features),
    onSuccess: (resultado) => {
      queryClient.setQueryData(['admin', 'tier-features', tierId], resultado);
      // A contagem "liberada em N de M planos" vive na tela de flags.
      void queryClient.invalidateQueries({
        queryKey: ['admin', 'feature-flags'],
      });
      void queryClient.invalidateQueries({ queryKey: ['feature-flags'] });
      onSaved?.();
    },
    onError: (erro) => onError?.(erro),
  });

  const alternar = (key: string, ligado: boolean) => {
    const proximas = ligado
      ? [...marcadas, key]
      : marcadas.filter((k) => k !== key);
    setMarcadas(proximas);
    mutation.mutate(proximas);
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
              className="flex items-center gap-3 rounded-xl border border-[#383838]/15 px-3 py-2.5"
            >
              <input
                id={`${tierId}-feature-${key}`}
                type="checkbox"
                checked={marcadas.includes(key)}
                disabled={disabled || mutation.isPending}
                onChange={(e) => alternar(key, e.target.checked)}
                className="h-4 w-4 rounded border-[#383838]/30"
              />
              <span className="text-[13px] font-semibold text-[#383838]">
                {FEATURE_FLAGS[key].label}
              </span>
            </label>
          ))}
        </div>
      )}

      <p className="text-[11px] text-[#383838]/50">
        Vale só depois que a funcionalidade estiver como “liberado” em
        Configurações gerais. Plano novo nasce com tudo desmarcado.
      </p>
    </div>
  );
}
