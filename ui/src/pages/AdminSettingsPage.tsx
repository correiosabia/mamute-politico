import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { AdminShell } from '@/components/layout/AdminShell';
import { FeatureFlagsPanel } from '@/components/admin/FeatureFlagsPanel';
import { TermListEditor } from '@/components/admin/TermListEditor';
import { MarcacoesConfigPanel } from '@/components/admin/MarcacoesConfigPanel';
import { fetchWordCloudTerms, saveWordCloudTerms } from '@/api/admin';

const VAZIO = { stopwords: [] as string[], excluded_terms: [] as string[] };

export default function AdminSettingsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['admin', 'word-cloud-terms'],
    queryFn: fetchWordCloudTerms,
    retry: false,
  });

  const [stopwords, setStopwords] = useState<string[]>([]);
  const [excluded, setExcluded] = useState<string[]>([]);

  useEffect(() => {
    if (!data) return;
    setStopwords([...(data.stopwords ?? [])].sort());
    setExcluded([...(data.excluded_terms ?? [])].sort());
  }, [data]);

  const salvo = data ?? VAZIO;
  const dirty = useMemo(() => {
    const igual = (a: string[], b: string[]) =>
      a.length === b.length && a.every((v, i) => v === b[i]);
    return (
      !igual(stopwords, [...(salvo.stopwords ?? [])].sort()) ||
      !igual(excluded, [...(salvo.excluded_terms ?? [])].sort())
    );
  }, [stopwords, excluded, salvo]);

  const mutation = useMutation({
    mutationFn: () =>
      saveWordCloudTerms({ stopwords, excluded_terms: excluded }),
    onSuccess: (result) => {
      queryClient.setQueryData(['admin', 'word-cloud-terms'], result);
      // A nuvem lê a lista pública; invalidar evita o usuário ver o filtro velho.
      void queryClient.invalidateQueries({ queryKey: ['word-cloud-terms'] });
      toast.success('Filtros da nuvem de palavras atualizados.');
    },
    onError: () => toast.error('Não foi possível salvar. Tente novamente.'),
  });

  return (
    <AdminShell footer="green">
      <div>
        <h1 className="text-[36px] font-bold leading-none text-[#393939] md:text-[48px]">
          Configurações gerais
        </h1>
        <p className="mt-1 text-[18px] font-normal text-[#383838]">
          Ajustes globais da plataforma. Valem na hora, sem redeploy.
        </p>
      </div>

      <FeatureFlagsPanel />

      {isLoading ? (
        <div className="mp-card flex items-center gap-2 bg-white p-6 text-[#383838]/60">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
          Carregando…
        </div>
      ) : isError ? (
        <div className="mp-card bg-white p-6 text-[#383838]">
          Não foi possível carregar as configurações. Recarregue a página.
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-[24px] font-bold leading-none text-[#090909]">
              Nuvem de palavras
            </h2>
            <div className="flex items-center gap-3">
              {dirty && (
                <span className="text-[13px] font-semibold text-[#b45309]">
                  Alterações não salvas
                </span>
              )}
              <button
                type="button"
                disabled={!dirty || mutation.isPending}
                onClick={() => mutation.mutate()}
                className="flex items-center gap-2 rounded-full bg-[#1b76ff] px-6 py-2 text-[13px] font-bold uppercase text-white transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {mutation.isPending && (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                )}
                Salvar
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-2">
            <TermListEditor
              title="Stopwords"
              description="Somem de dentro de expressões, palavra a palavra. O resto da expressão continua na nuvem."
              example='"o projeto de lei" vira "lei"'
              terms={stopwords}
              onChange={setStopwords}
            />
            <TermListEditor
              title="Termos irrelevantes"
              description="Descartam a entrada inteira quando ela bate por completo. Nada sobra na nuvem."
              example='"mudança climática" some por completo'
              terms={excluded}
              onChange={setExcluded}
            />
          </div>

          <p className="text-[13px] leading-relaxed text-[#383838]/70">
            Na dúvida entre as duas listas, prefira <strong>termos irrelevantes</strong>.
            Palavras ambíguas como “união” ou “podemos” são siglas de partido, mas
            também palavras comuns: como stopword elas mutilariam expressões
            legítimas (“união estável” viraria “estável”).
          </p>
        </>
      )}

      <div className="mt-10 border-t border-black/10 pt-8">
        <MarcacoesConfigPanel />
      </div>
    </AdminShell>
  );
}
