import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueries, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { toast } from 'sonner';
import { Header } from '@/components/layout/Header';
import { CongressoSelector } from '@/components/selecao/CongressoSelector';
import { ParlamentarSelector } from '@/components/selecao/ParlamentarSelector';
import { SelecaoFooter } from '@/components/selecao/SelecaoFooter';
import { CasaLegislativa, Parlamentar } from '@/types/parlamentar';
import {
  listMyProjectFavorites,
  getMyProjectFavoritesQuota,
  addMyProjectFavorite,
  removeMyProjectFavorite,
  reorderMyProjectFavorites,
  getParliamentarian,
  listMyProjectTags,
  createMyProjectTag,
  listMyParliamentarianTags,
  setMyParliamentarianTags,
  getMarcacoesSettings,
  listMyMamutometro,
  setMyMamutometro,
  clearMyMamutometro,
} from '@/api/endpoints';
import type { ProjectFavoriteOut } from '@/api/types';
import { ApiError } from '@/api/client';
import { mapParliamentarianOutToParlamentar } from '@/api/mappers';
import { useFeatureFlag } from '@/hooks/useFeatureFlag';
import { ArrowLeft, ArrowRight } from 'lucide-react';

const MAX_TAGS_POR_PARLAMENTAR = 10;

const CASA_HASH: Record<CasaLegislativa, string> = {
  senado: '#senado-federal',
  ambas: '#ambas-casas',
  camara: '#camara-dos-deputados',
};

const getCasaFromHash = (hash: string): CasaLegislativa | null =>
  (Object.entries(CASA_HASH).find(([, casaHash]) => casaHash === hash)?.[0] as CasaLegislativa | undefined) ?? null;

const SelecaoPage = () => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const casaSelecionada = getCasaFromHash(location.hash);
  const [recentlyAdded, setRecentlyAdded] = useState<Parlamentar | null>(null);
  const marcacoesPessoaisOn = useFeatureFlag('marcacoes_pessoais');
  const mamutometroFlagOn = useFeatureFlag('mamutometro');
  const [filtroTagId, setFiltroTagId] = useState<number | null>(null);

  const favoritesQuery = useQuery({
    queryKey: ['project-favorites', 'me'],
    queryFn: () => listMyProjectFavorites(),
    enabled: casaSelecionada != null,
  });
  const favoritesQuotaQuery = useQuery({
    queryKey: ['project-favorites-quota', 'me'],
    queryFn: () => getMyProjectFavoritesQuota(),
    enabled: casaSelecionada != null,
  });

  const favoriteIds = favoritesQuery.data?.map((f) => f.parliamentarian_id) ?? [];
  const parliamentarianQueries = useQueries({
    queries: favoriteIds.map((id) => ({
      queryKey: ['parliamentarian', id],
      queryFn: () => getParliamentarian(id),
    })),
  });

  const parlamentaresMonitorados: Parlamentar[] = parliamentarianQueries
    .filter((q) => q.data != null)
    .map((q) => mapParliamentarianOutToParlamentar(q.data!));

  const monitoradosLoading =
    favoritesQuery.isLoading ||
    (favoriteIds.length > 0 && parliamentarianQueries.some((q) => q.isLoading));

  const monitoradosError =
    favoritesQuery.isError && !monitoradosLoading
      ? favoritesQuery.error instanceof ApiError
        ? favoritesQuery.error.message
        : favoritesQuery.error instanceof Error
          ? favoritesQuery.error.message
          : 'Não foi possível carregar os favoritos.'
      : null;

  const addMutation = useMutation({
    mutationFn: (parlamentar: Parlamentar) => addMyProjectFavorite(Number(parlamentar.id)),
    onSuccess: (_favorite, parlamentar) => {
      setRecentlyAdded(parlamentar);
      toast.success(`${parlamentar.nome} adicionado aos monitorados.`);
      void queryClient.invalidateQueries({ queryKey: ['project-favorites', 'me'] });
      void queryClient.invalidateQueries({ queryKey: ['project-favorites-quota', 'me'] });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        toast.info('Este parlamentar já está nos favoritos.');
        void queryClient.invalidateQueries({ queryKey: ['project-favorites', 'me'] });
        void queryClient.invalidateQueries({ queryKey: ['project-favorites-quota', 'me'] });
        return;
      }
      if (error instanceof ApiError && error.status === 403) {
        toast.info(error.message);
        void queryClient.invalidateQueries({ queryKey: ['project-favorites-quota', 'me'] });
        return;
      }
      const msg =
        error instanceof Error ? error.message : 'Não foi possível adicionar o favorito.';
      toast.error(msg);
    },
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => removeMyProjectFavorite(Number(id)),
    onSuccess: (_favorite, id) => {
      if (recentlyAdded?.id === id) {
        setRecentlyAdded(null);
      }
      void queryClient.invalidateQueries({ queryKey: ['project-favorites', 'me'] });
      void queryClient.invalidateQueries({ queryKey: ['project-favorites-quota', 'me'] });
    },
    onError: (error) => {
      const msg =
        error instanceof Error ? error.message : 'Não foi possível remover o favorito.';
      toast.error(msg);
    },
  });

  const reorderMutation = useMutation({
    mutationFn: (orderedIds: number[]) => reorderMyProjectFavorites(orderedIds),
    onMutate: async (orderedIds) => {
      await queryClient.cancelQueries({ queryKey: ['project-favorites', 'me'] });
      const anterior = queryClient.getQueryData<ProjectFavoriteOut[]>([
        'project-favorites',
        'me',
      ]);
      if (anterior) {
        const porParlamentar = new Map(anterior.map((f) => [f.parliamentarian_id, f]));
        const otimista = orderedIds
          .map((id) => porParlamentar.get(id))
          .filter((f): f is ProjectFavoriteOut => f != null);
        queryClient.setQueryData(['project-favorites', 'me'], otimista);
      }
      return { anterior };
    },
    onSuccess: (favoritos) => {
      queryClient.setQueryData(['project-favorites', 'me'], favoritos);
    },
    onError: (error, _orderedIds, context) => {
      if (context?.anterior) {
        queryClient.setQueryData(['project-favorites', 'me'], context.anterior);
      }
      if (error instanceof ApiError && error.status === 422) {
        toast.info('Sua lista de monitorados mudou. Atualizamos aqui — ordene de novo.');
        void queryClient.invalidateQueries({ queryKey: ['project-favorites', 'me'] });
        return;
      }
      const msg =
        error instanceof Error ? error.message : 'Não foi possível salvar a ordem.';
      toast.error(msg);
    },
  });

  const handleReorderParlamentares = (orderedIds: string[]) => {
    reorderMutation.mutate(orderedIds.map(Number));
  };

  const tagsQuery = useQuery({
    queryKey: ['project-tags', 'me'],
    queryFn: () => listMyProjectTags(),
    enabled: marcacoesPessoaisOn && casaSelecionada != null,
  });
  const parlamentarTagsQuery = useQuery({
    queryKey: ['parliamentarian-tags', 'me'],
    queryFn: () => listMyParliamentarianTags(),
    enabled: marcacoesPessoaisOn && casaSelecionada != null,
  });

  const tagIdsPorParlamentar: Record<string, number[]> = {};
  for (const linha of parlamentarTagsQuery.data ?? []) {
    tagIdsPorParlamentar[String(linha.parliamentarian_id)] = linha.tag_ids;
  }

  const avisarErroDeTag = (error: unknown, fallback: string) => {
    // 409 (tag repetida) e 422 (teto) são situações previstas, com texto pronto
    // vindo da API — informam, não alarmam.
    if (error instanceof ApiError && (error.status === 409 || error.status === 422)) {
      toast.info(error.message);
      return;
    }
    toast.error(error instanceof Error ? error.message : fallback);
  };

  const alterarTagsMutation = useMutation({
    mutationFn: ({ parlamentarId, tagIds }: { parlamentarId: string; tagIds: number[] }) =>
      setMyParliamentarianTags(Number(parlamentarId), tagIds),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['parliamentarian-tags', 'me'] });
      void queryClient.invalidateQueries({ queryKey: ['project-tags', 'me'] });
    },
    onError: (error) => avisarErroDeTag(error, 'Não foi possível salvar as tags.'),
  });

  const criarTagMutation = useMutation({
    mutationFn: ({ nome }: { nome: string; parlamentarId: string }) =>
      createMyProjectTag(nome),
    onSuccess: (tag, { parlamentarId }) => {
      void queryClient.invalidateQueries({ queryKey: ['project-tags', 'me'] });
      const atuais = tagIdsPorParlamentar[parlamentarId] ?? [];
      alterarTagsMutation.mutate({ parlamentarId, tagIds: [...atuais, tag.id] });
    },
    onError: (error) => avisarErroDeTag(error, 'Não foi possível criar a tag.'),
  });

  // --- Mamutômetro (SPEC-001, fatia 4) ---
  // Duas condições para existir: a flag (rollout) e o plano (comercial). O
  // backend já resolve a segunda em `enabled` — a tela não repete a regra.
  const marcacoesSettingsQuery = useQuery({
    queryKey: ['marcacoes-settings'],
    queryFn: () => getMarcacoesSettings(),
    enabled: mamutometroFlagOn && casaSelecionada != null,
    staleTime: 5 * 60 * 1000,
  });
  const mamutometroConfig = marcacoesSettingsQuery.data?.mamutometro;
  const mamutometroAtivo = mamutometroFlagOn && mamutometroConfig?.enabled === true;

  const mamutometroQuery = useQuery({
    queryKey: ['mamutometro', 'me'],
    queryFn: () => listMyMamutometro(),
    enabled: mamutometroAtivo,
  });

  const niveisPorParlamentar: Record<string, number> = {};
  for (const marca of mamutometroQuery.data ?? []) {
    niveisPorParlamentar[String(marca.parliamentarian_id)] = marca.level;
  }

  const mamutometroMutation = useMutation({
    mutationFn: async ({
      parlamentarId,
      level,
    }: {
      parlamentarId: string;
      level: number | null;
    }): Promise<void> => {
      // null = limpar. Duas rotas, um só ponto de entrada, para o componente
      // não precisar saber que "remover" é um verbo HTTP diferente.
      if (level == null) {
        await clearMyMamutometro(Number(parlamentarId));
        return;
      }
      await setMyMamutometro(Number(parlamentarId), level);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['mamutometro', 'me'] });
      // `used` faz parte da config resolvida, então ela recarrega junto.
      void queryClient.invalidateQueries({ queryKey: ['marcacoes-settings'] });
    },
    onError: (error) => {
      // 403 = teto do plano, com a mensagem de upgrade pronta vinda da API.
      if (error instanceof ApiError && (error.status === 403 || error.status === 422)) {
        toast.info(error.message);
        return;
      }
      toast.error(
        error instanceof Error ? error.message : 'Não foi possível salvar a marcação.',
      );
    },
  });

  const handleSelectCasa = (casa: CasaLegislativa) => {
    navigate({ pathname: '/selecao', hash: CASA_HASH[casa] });
  };

  const handleAddParlamentar = (parlamentar: Parlamentar) => {
    addMutation.mutate(parlamentar);
  };

  const handleRemoveParlamentar = (id: string) => {
    removeMutation.mutate(id);
  };

  const handleBack = () => {
    navigate('/selecao');
  };

  const favoritosMutating = addMutation.isPending || removeMutation.isPending;

  const casaLabel =
    casaSelecionada === 'senado'
      ? 'Senado Federal'
      : casaSelecionada === 'camara'
        ? 'Câmara dos Deputados'
        : 'Ambas as Casas';

  return (
    <div className="min-h-screen bg-textura-gold">
      <Header />

      {!casaSelecionada ? (
        <CongressoSelector onSelect={handleSelectCasa} selected={casaSelecionada} />
      ) : (
        <main className="min-h-[calc(100vh-64px)]">
          {/* Yellow top section with title */}
          <div className="bg-textura-gold px-6 py-10">
            <div className="container">
              <h1 className="text-center text-[36px] md:text-[48px] leading-none font-bold text-[#393939]">{casaLabel}</h1>
              <div className="mt-6 flex flex-wrap items-center justify-center gap-[16px] md:justify-between">
                <button
                  type="button"
                  onClick={handleBack}
                  className="flex items-center min-w-[250px] gap-2 rounded-[76px] bg-white px-6 py-2 text-[13px] font-semibold text-[#383838] shadow-sm transition hover:opacity-90"
                >
                  <ArrowLeft className="h-4 w-4" />
                  VOLTAR À SELEÇÃO DE CASA
                </button>
                
                <Link
                  to="/dashboard"
                  className="flex items-center min-w-[250px] gap-2 rounded-[76px] bg-[#393939] px-6 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:opacity-90"
                >
                  VER DASHBOARD GERAL
                  <ArrowRight className="h-4 w-4" />
                </Link>
                
              </div>
            </div>
          </div>

          {/* Gray bottom section with parlamentar selector */}
          <div className="md:px-6 py-8">
            <div className="container">
              <ParlamentarSelector
                casaSelecionada={casaSelecionada}
                parlamentaresSelecionados={parlamentaresMonitorados}
                onAddParlamentar={handleAddParlamentar}
                onRemoveParlamentar={handleRemoveParlamentar}
                monitoradosLoading={monitoradosLoading}
                monitoradosError={monitoradosError}
                favoritosMutating={favoritosMutating}
                monitoradosLimit={
                  favoritesQuotaQuery.data?.unlimited
                    ? null // admin: sem limite — o seletor trata null como ilimitado
                    : (favoritesQuotaQuery.data?.limit ?? null)
                }
                monitoradosUsed={favoritesQuotaQuery.data?.used ?? favoriteIds.length}
                monitoradosQuotaLoading={favoritesQuotaQuery.isLoading}
                recentlyAdded={recentlyAdded}
                onReorderParlamentares={
                  marcacoesPessoaisOn ? handleReorderParlamentares : undefined
                }
                mamutometro={
                  mamutometroAtivo && mamutometroConfig
                    ? {
                        maxLevel: mamutometroConfig.max_level,
                        noticeText: mamutometroConfig.notice_text,
                        niveis: niveisPorParlamentar,
                        salvando: mamutometroMutation.isPending,
                        onChange: (parlamentarId, level) =>
                          mamutometroMutation.mutate({ parlamentarId, level }),
                      }
                    : null
                }
                tagsPessoais={
                  marcacoesPessoaisOn
                    ? {
                        tags: tagsQuery.data ?? [],
                        tagIdsPorParlamentar,
                        filtroTagId,
                        maxTagsPorParlamentar: MAX_TAGS_POR_PARLAMENTAR,
                        salvando:
                          alterarTagsMutation.isPending || criarTagMutation.isPending,
                        onFiltrarPorTag: setFiltroTagId,
                        onAlterarTags: (parlamentarId, tagIds) =>
                          alterarTagsMutation.mutate({ parlamentarId, tagIds }),
                        onCriarTag: (nome, parlamentarId) =>
                          criarTagMutation.mutate({ nome, parlamentarId }),
                      }
                    : null
                }
                reorderPending={reorderMutation.isPending}
                monitoradosQuota={
                  favoritesQuotaQuery.data
                    ? {
                        camara: favoritesQuotaQuery.data.camara,
                        senado: favoritesQuotaQuery.data.senado,
                      }
                    : null
                }
              />
            </div>
          </div>

          <SelecaoFooter />
        </main>
      )}
    </div>
  );
};

export default SelecaoPage;
