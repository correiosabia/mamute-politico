import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueries, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Header } from '@/components/layout/Header';
import { CongressoSelector } from '@/components/selecao/CongressoSelector';
import { ParlamentarSelector } from '@/components/selecao/ParlamentarSelector';
import { SelecaoFooter } from '@/components/selecao/SelecaoFooter';
import { CasaLegislativa, Parlamentar } from '@/types/parlamentar';
import {
  listMyProjectFavorites,
  addMyProjectFavorite,
  removeMyProjectFavorite,
  getParliamentarian,
} from '@/api/endpoints';
import { ApiError } from '@/api/client';
import { mapParliamentarianOutToParlamentar } from '@/api/mappers';
import { ArrowLeft, ArrowRight } from 'lucide-react';

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

  const favoritesQuery = useQuery({
    queryKey: ['project-favorites', 'me'],
    queryFn: () => listMyProjectFavorites(),
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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['project-favorites', 'me'] });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        toast.info('Este parlamentar já está nos favoritos.');
        void queryClient.invalidateQueries({ queryKey: ['project-favorites', 'me'] });
        return;
      }
      const msg =
        error instanceof Error ? error.message : 'Não foi possível adicionar o favorito.';
      toast.error(msg);
    },
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => removeMyProjectFavorite(Number(id)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['project-favorites', 'me'] });
    },
    onError: (error) => {
      const msg =
        error instanceof Error ? error.message : 'Não foi possível remover o favorito.';
      toast.error(msg);
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
