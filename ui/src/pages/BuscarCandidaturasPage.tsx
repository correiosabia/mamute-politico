import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Filter, Loader2, Plus, X } from 'lucide-react';

import { Header } from '@/components/layout/Header';
import { CandidaturasFooter } from '@/components/layout/CandidaturasFooter';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { LazyAvatarImage } from '@/components/ui/lazy-avatar-image';
import { cn } from '@/lib/utils';
import {
  addMyProjectFavorite,
  getCandidacyFilters,
  listCandidacies,
  listMyProjectFavorites,
} from '@/api/endpoints';
import type { CandidacyOut } from '@/api/types';
import { ApiError } from '@/api/client';

/** Página de resultados. O backend limita a 200; 50 cobre a lista com scroll do design. */
const RESULTS_LIMIT = 50;

/** O backend exige 2+ caracteres — barra aqui para não gastar request num 422. */
const MIN_NOME = 2;

/**
 * O Radix não aceita `value=""` num item, então "sem filtro" tem valor próprio.
 * Já o *root* do Select recebe `undefined` enquanto nada foi escolhido — é o que
 * faz aparecer o placeholder ("selecionar estado") em vez do rótulo do item.
 */
const TODOS = '__todos__';
const SEM_SELECAO = '';

/**
 * Rótulo curto do badge por código de cargo da DivulgaCandContas. O design traz
 * só o caso do Senado ("SENADO"); os outros seguem a mesma lógica de instância
 * disputada e estão pendentes de confirmação do designer.
 */
const BADGE_POR_CARGO: Record<number, string> = {
  1: 'PRESIDÊNCIA',
  3: 'GOVERNO',
  5: 'SENADO',
  6: 'CÂMARA',
  7: 'ASSEMBLEIA',
  8: 'CÂMARA DISTRITAL',
};

interface FiltrosAplicados {
  nome?: string;
  estado?: string;
  officeCode?: number;
}

const badgeLabel = (candidatura: CandidacyOut): string => {
  if (candidatura.office_code != null && BADGE_POR_CARGO[candidatura.office_code]) {
    return BADGE_POR_CARGO[candidatura.office_code];
  }
  return (candidatura.office ?? 'CANDIDATURA').toUpperCase();
};

const iniciais = (nome: string): string =>
  nome
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((parte) => parte[0]?.toUpperCase() ?? '')
    .join('');

const BuscarCandidaturasPage = () => {
  const queryClient = useQueryClient();

  // Estado do formulário do herói (o design tem botão PESQUISAR explícito, então
  // digitar não dispara busca) e o estado efetivamente aplicado à listagem.
  const [nomeInput, setNomeInput] = useState('');
  const [estadoInput, setEstadoInput] = useState<string>(SEM_SELECAO);
  const [cargoInput, setCargoInput] = useState<string>(SEM_SELECAO);
  const [filtros, setFiltros] = useState<FiltrosAplicados>({});
  const [painelFiltrosAberto, setPainelFiltrosAberto] = useState(false);

  const filtersQuery = useQuery({
    queryKey: ['candidacy-filters'],
    queryFn: () => getCandidacyFilters(),
  });

  const candidaciesQuery = useQuery({
    queryKey: ['candidacies', filtros],
    queryFn: () =>
      listCandidacies({
        limit: RESULTS_LIMIT,
        name: filtros.nome,
        state: filtros.estado,
        office_code: filtros.officeCode,
      }),
  });

  const favoritesQuery = useQuery({
    queryKey: ['project-favorites', 'me'],
    queryFn: () => listMyProjectFavorites(),
  });

  const monitoradosIds = useMemo(
    () => new Set((favoritesQuery.data ?? []).map((f) => f.parliamentarian_id)),
    [favoritesQuery.data]
  );

  const addMutation = useMutation({
    mutationFn: ({ id }: { id: number; nome: string }) => addMyProjectFavorite(id),
    onSuccess: (_favorite, { nome }) => {
      toast.success(`${nome} adicionado(a) aos monitorados.`);
      void queryClient.invalidateQueries({ queryKey: ['project-favorites', 'me'] });
      void queryClient.invalidateQueries({ queryKey: ['project-favorites-quota', 'me'] });
    },
    onError: (error) => {
      // Mesmo tratamento da Seleção: 409 é "já monitorado" e 403 é cota cheia —
      // nenhum dos dois é erro para o usuário.
      if (error instanceof ApiError && error.status === 409) {
        toast.info('Este parlamentar já está nos monitorados.');
        void queryClient.invalidateQueries({ queryKey: ['project-favorites', 'me'] });
        return;
      }
      if (error instanceof ApiError && error.status === 403) {
        toast.info(error.message);
        return;
      }
      toast.error(
        error instanceof Error ? error.message : 'Não foi possível adicionar aos monitorados.'
      );
    },
  });

  /** `undefined` mantém o placeholder do design enquanto nada foi escolhido. */
  const valorSelect = (v: string) => (v === SEM_SELECAO ? undefined : v);

  const aplicarBusca = () => {
    const nome = nomeInput.trim();
    if (nome.length === 1) {
      toast.info(`Digite pelo menos ${MIN_NOME} caracteres para buscar por nome.`);
      return;
    }
    setFiltros({
      nome: nome.length >= MIN_NOME ? nome : undefined,
      estado: estadoInput === TODOS || estadoInput === SEM_SELECAO ? undefined : estadoInput,
      officeCode:
        cargoInput === TODOS || cargoInput === SEM_SELECAO ? undefined : Number(cargoInput),
    });
  };

  /** Filtro mexido dentro do card aplica na hora e mantém o herói em sincronia. */
  const aplicarEstado = (valor: string) => {
    setEstadoInput(valor);
    setFiltros((atual) => ({
      ...atual,
      estado: valor === TODOS || valor === SEM_SELECAO ? undefined : valor,
    }));
  };

  const aplicarCargo = (valor: string) => {
    setCargoInput(valor);
    setFiltros((atual) => ({
      ...atual,
      officeCode: valor === TODOS || valor === SEM_SELECAO ? undefined : Number(valor),
    }));
  };

  const removerFiltroNome = () => {
    setNomeInput('');
    setFiltros((atual) => ({ ...atual, nome: undefined }));
  };

  const cargoLabel = (code: number): string =>
    filtersQuery.data?.offices.find((o) => o.code === code)?.name ?? String(code);

  const chips: Array<{ id: string; label: string; onRemove: () => void }> = [];
  if (filtros.nome) {
    chips.push({ id: 'nome', label: filtros.nome, onRemove: removerFiltroNome });
  }
  if (filtros.estado) {
    chips.push({
      id: 'estado',
      label: filtros.estado,
      onRemove: () => aplicarEstado(TODOS),
    });
  }
  if (filtros.officeCode != null) {
    chips.push({
      id: 'cargo',
      label: cargoLabel(filtros.officeCode),
      onRemove: () => aplicarCargo(TODOS),
    });
  }

  const candidaturas = candidaciesQuery.data ?? [];

  const pillInput =
    'h-10 rounded-[76px] border-0 bg-[#efeeee] px-5 text-[14px] text-[#383838] italic placeholder:italic placeholder:text-[#7f7b7b] focus:outline-none focus:ring-2 focus:ring-white/70';

  return (
    <div className="flex min-h-screen flex-col bg-[#f1f1f1]">
      <div className="bg-[#1b76ff]">
        <Header tone="blue" actions="busca" />

        <section className="container pb-28 pt-10 text-center md:pb-32">
          <h1 className="text-[36px] font-bold leading-tight text-white md:text-[48px]">
            Buscar Candidaturas
          </h1>
          <p className="mx-auto mt-3 max-w-[560px] text-[16px] leading-normal text-white/90">
            Confira informações detalhadas sobre todos os candidatos que pediram registro à Justiça
            Eleitoral
          </p>

          <form
            className="mt-8 flex flex-col items-stretch justify-center gap-3 md:flex-row md:items-center"
            onSubmit={(event) => {
              event.preventDefault();
              aplicarBusca();
            }}
          >
            <input
              type="search"
              value={nomeInput}
              onChange={(event) => setNomeInput(event.target.value)}
              placeholder="busca por nome"
              aria-label="Busca por nome"
              className={cn(pillInput, 'md:w-[360px]')}
            />

            <Select value={valorSelect(estadoInput)} onValueChange={setEstadoInput}>
              <SelectTrigger
                aria-label="Selecionar estado"
                className={cn(pillInput, 'justify-between md:w-[210px]')}
              >
                <SelectValue placeholder="selecionar estado" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>todos os estados</SelectItem>
                {(filtersQuery.data?.states ?? []).map((uf) => (
                  <SelectItem key={uf} value={uf}>
                    {uf}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={valorSelect(cargoInput)} onValueChange={setCargoInput}>
              <SelectTrigger
                aria-label="Selecionar cargo"
                className={cn(pillInput, 'justify-between md:w-[210px]')}
              >
                <SelectValue placeholder="selecionar cargo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>todos os cargos</SelectItem>
                {(filtersQuery.data?.offices ?? []).map((office) => (
                  <SelectItem key={office.code} value={String(office.code)}>
                    {office.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <button
              type="submit"
              className="h-10 rounded-[76px] bg-white px-7 text-[13px] font-bold uppercase tracking-wide text-[#1b76ff] transition hover:opacity-90"
            >
              PESQUISAR
            </button>
          </form>
        </section>
      </div>

      {/* O card sobrepõe a divisa do azul com o fundo claro, como no design. */}
      <main className="container -mt-20 flex-1 pb-16 md:-mt-24">
        <div className="rounded-[28px] bg-white p-6 shadow-[0_14px_34px_rgba(0,0,0,0.10)] md:p-8">
          <h2 className="text-[24px] font-bold text-[#090909] md:text-[28px]">
            Resultados da busca
          </h2>

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setPainelFiltrosAberto((aberto) => !aberto)}
              aria-expanded={painelFiltrosAberto}
              aria-controls="painel-filtros-candidaturas"
              className={cn(
                'inline-flex items-center gap-2 rounded-[76px] border px-4 py-1.5 text-[13px] italic transition',
                painelFiltrosAberto
                  ? 'border-[#1b76ff] text-[#1b76ff]'
                  : 'border-[#d9d9d9] text-[#7f7b7b] hover:border-[#7f7b7b]'
              )}
            >
              <Filter className="h-4 w-4" aria-hidden="true" />
              Filtros
            </button>

            {chips.map((chip) => (
              <span
                key={chip.id}
                className="inline-flex items-center gap-2 rounded-[76px] bg-[#7f7c7c] px-3 py-1.5 text-[12px] font-bold text-white"
              >
                {chip.label}
                <button
                  type="button"
                  onClick={chip.onRemove}
                  aria-label={`Remover filtro ${chip.label}`}
                  className="transition hover:opacity-70"
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </span>
            ))}
          </div>

          {painelFiltrosAberto && (
            <div
              id="painel-filtros-candidaturas"
              className="mt-4 flex flex-col gap-3 rounded-2xl bg-[#f9f9f9] p-4 md:flex-row md:items-center"
            >
              <Select value={valorSelect(estadoInput)} onValueChange={aplicarEstado}>
                <SelectTrigger aria-label="Filtrar por estado" className="md:w-[210px]">
                  <SelectValue placeholder="selecionar estado" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={TODOS}>todos os estados</SelectItem>
                  {(filtersQuery.data?.states ?? []).map((uf) => (
                    <SelectItem key={uf} value={uf}>
                      {uf}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select value={valorSelect(cargoInput)} onValueChange={aplicarCargo}>
                <SelectTrigger aria-label="Filtrar por cargo" className="md:w-[210px]">
                  <SelectValue placeholder="selecionar cargo" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={TODOS}>todos os cargos</SelectItem>
                  {(filtersQuery.data?.offices ?? []).map((office) => (
                    <SelectItem key={office.code} value={String(office.code)}>
                      {office.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="mt-5 max-h-[420px] overflow-y-auto pr-1">
            {candidaciesQuery.isLoading ? (
              <p className="flex items-center gap-2 py-10 text-center text-[14px] text-[#7f7b7b]">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Carregando candidaturas...
              </p>
            ) : candidaciesQuery.isError ? (
              <p className="py-10 text-[14px] text-[#c0392b]">
                {candidaciesQuery.error instanceof Error
                  ? candidaciesQuery.error.message
                  : 'Não foi possível carregar as candidaturas.'}
              </p>
            ) : candidaturas.length === 0 ? (
              <p className="py-10 text-[14px] text-[#7f7b7b]">
                Nenhuma candidatura encontrada com esses filtros.
              </p>
            ) : (
              <ul className="flex flex-col gap-3">
                {candidaturas.map((candidatura) => {
                  const nome = candidatura.ballot_name ?? candidatura.full_name ?? 'Sem nome';
                  const partidoUf = [candidatura.party, candidatura.state]
                    .filter(Boolean)
                    .join(' - ');
                  const monitorado =
                    candidatura.parliamentarian_id != null &&
                    monitoradosIds.has(candidatura.parliamentarian_id);
                  // Monitoramento é por parlamentar; candidatura sem vínculo na
                  // base não tem o que monitorar ainda.
                  const podeMonitorar = candidatura.parliamentarian_id != null;
                  // Só o botão em voo desabilita — travar a lista toda a cada
                  // clique deixaria a impressão de tela congelada.
                  const adicionando =
                    addMutation.isPending &&
                    addMutation.variables?.id === candidatura.parliamentarian_id;

                  return (
                    <li
                      key={candidatura.id}
                      className="flex items-center gap-4 rounded-[20px] border border-[#efeeee] px-4 py-3"
                    >
                      <LazyAvatarImage
                        src={candidatura.photo_url ?? undefined}
                        alt={nome}
                        fallback={iniciais(nome)}
                        className="h-11 w-11 shrink-0"
                      />

                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[15px] font-bold text-[#090909]">{nome}</p>
                        <div className="mt-1 flex flex-wrap items-center gap-2">
                          <span className="rounded-[76px] bg-[#09e03b] px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
                            {badgeLabel(candidatura)}
                          </span>
                          {partidoUf && (
                            <span className="text-[12px] font-medium text-[#7f7b7b]">
                              {partidoUf}
                            </span>
                          )}
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => {
                          if (candidatura.parliamentarian_id != null) {
                            addMutation.mutate({ id: candidatura.parliamentarian_id, nome });
                          }
                        }}
                        disabled={!podeMonitorar || monitorado || adicionando}
                        title={
                          !podeMonitorar
                            ? 'Esta candidatura ainda não está vinculada a um parlamentar na base — monitoramento indisponível.'
                            : monitorado
                              ? 'Já está nos seus monitorados'
                              : 'Adicionar aos monitorados'
                        }
                        aria-label={
                          monitorado
                            ? `${nome} já está nos monitorados`
                            : `Adicionar ${nome} aos monitorados`
                        }
                        className={cn(
                          'flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 transition',
                          monitorado
                            ? 'border-[#09a03b] bg-[#09a03b] text-white'
                            : 'border-[#09a03b] text-[#09a03b] hover:bg-[#09a03b]/10',
                          !podeMonitorar && 'cursor-not-allowed border-[#d9d9d9] text-[#d9d9d9] hover:bg-transparent'
                        )}
                      >
                        {monitorado ? (
                          <Check className="h-5 w-5" aria-hidden="true" />
                        ) : (
                          <Plus className="h-5 w-5" aria-hidden="true" />
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      </main>

      <CandidaturasFooter />
    </div>
  );
};

export default BuscarCandidaturasPage;
