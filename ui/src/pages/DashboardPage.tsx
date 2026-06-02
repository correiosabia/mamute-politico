import { useEffect, useRef, useState, type MouseEventHandler } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueries } from '@tanstack/react-query';
import { Header } from '@/components/layout/Header';
import { Timeline } from '@/components/dashboard/Timeline';
import { ProposicoesList } from '@/components/dashboard/ProposicoesList';
import {
  listMyProjectFavorites,
  getParliamentarian,
  getMyDashboardActivity,
} from '@/api/endpoints';
import { ApiError } from '@/api/client';
import { mapParliamentarianOutToParlamentar } from '@/api/mappers';
import { sortByNome } from '@/lib/utils';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Loader2, Pencil, Users } from 'lucide-react';
import banner3 from '@/assets/banner3-semfundo.png';
import logoMamute from '@/assets/logo-mamute.png';

const MONITORADOS_AMBAS_CASAS_LINK = '/selecao#ambas-casas';

const DashboardPage = () => {
  const MOBILE_BREAKPOINT_PX = 768;
  const FOOTER_PERSPECTIVE_PX = 1200;
  const FOOTER_MAX_ROTATE_Y_DEG = 2;
  const FOOTER_MAX_TRANSLATE_X_PX = 20;
  const FOOTER_SCALE = 1.02;
  const [isMobileViewport, setIsMobileViewport] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < MOBILE_BREAKPOINT_PX : false
  );
  const footerImageRef = useRef<HTMLDivElement | null>(null);
  const [footerImageTransform, setFooterImageTransform] = useState(
    `perspective(${FOOTER_PERSPECTIVE_PX}px) rotateY(0deg) translateX(0px) scale(${FOOTER_SCALE})`
  );

  useEffect(() => {
    const handleResize = () => {
      setIsMobileViewport(window.innerWidth < MOBILE_BREAKPOINT_PX);
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  const handleFooterMouseMove: MouseEventHandler<HTMLElement> = (event) => {
    const rect = footerImageRef.current?.getBoundingClientRect() ?? event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const clampedX = Math.min(1, Math.max(0, x));
    const centered = (clampedX - 0.5) * 2;

    const rotateY = centered * -FOOTER_MAX_ROTATE_Y_DEG;
    const translateX = centered * -FOOTER_MAX_TRANSLATE_X_PX;
    setFooterImageTransform(
      `perspective(${FOOTER_PERSPECTIVE_PX}px) rotateY(${rotateY.toFixed(2)}deg) translateX(${translateX.toFixed(2)}px) scale(${FOOTER_SCALE})`
    );
  };

  const handleFooterMouseLeave = () => {
    setFooterImageTransform(
      `perspective(${FOOTER_PERSPECTIVE_PX}px) rotateY(0deg) translateX(0px) scale(${FOOTER_SCALE})`
    );
  };

  const favoritesQuery = useQuery({
    queryKey: ['project-favorites', 'me'],
    queryFn: () => listMyProjectFavorites(),
  });

  const favoriteIds = favoritesQuery.data?.map((f) => f.parliamentarian_id) ?? [];
  const parliamentarianQueries = useQueries({
    queries: favoriteIds.map((id) => ({
      queryKey: ['parliamentarian', id],
      queryFn: () => getParliamentarian(id),
    })),
  });

  const monitorados = sortByNome(
    parliamentarianQueries
      .filter((q) => q.data != null)
      .map((q) => mapParliamentarianOutToParlamentar(q.data!)),
  );

  const isLoadingMonitorados =
    favoritesQuery.isLoading ||
    (favoriteIds.length > 0 && parliamentarianQueries.some((q) => q.isLoading));

  const favoritesError = favoritesQuery.error;
  const monitoradosErrorMessage =
    favoritesError instanceof ApiError
      ? favoritesError.message
      : favoritesError instanceof Error
        ? favoritesError.message
        : 'Não foi possível carregar os favoritos.';

  const dashboardActivityQuery = useQuery({
    queryKey: ['dashboard-activity', 'me', { limit: 20 }],
    queryFn: () => getMyDashboardActivity({ limit: 20 }),
  });

  const dashboardActivity = dashboardActivityQuery.data;

  return (
    <div className="min-h-screen bg-textura-gold">
      <Header />

      <main className="container py-10 space-y-6">
        {/* Page header */}
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-[36px] md:text-[48px] font-bold leading-none text-[#393939]">
              Dashboard Geral
            </h1>
            <p className="mt-1 text-[18px] font-normal text-[#383838]">
              Acompanhe a atividade dos parlamentares monitorados
            </p>
          </div>
          <Link
            to={MONITORADOS_AMBAS_CASAS_LINK}
            className="group flex items-center gap-2 self-start rounded-full bg-[#1b76ff] px-5 py-2 text-[13px] font-semibold text-white no-underline transition-opacity hover:opacity-90"
          >
            <span className="relative inline-flex h-4 w-4 shrink-0 items-center justify-center">
              <Users className="h-4 w-4 transition-opacity duration-150 group-hover:opacity-0" />
              <Pencil className="absolute h-4 w-4 opacity-0 transition-opacity duration-150 group-hover:opacity-100" />
            </span>
            {monitorados.length} PARLAMENTAR{monitorados.length !== 1 ? 'ES' : ''} MONITORADO{monitorados.length !== 1 ? 'S' : ''}
          </Link>
        </div>

        {/* Parlamentares monitorados */}
        <div className="mp-card bg-white p-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-[32px] leading-none font-bold text-[#090909]">
              <Link to={MONITORADOS_AMBAS_CASAS_LINK} className="underline-offset-4 transition hover:underline">
                Parlamentares monitorados
              </Link>
            </h2>
            <Link
              to={MONITORADOS_AMBAS_CASAS_LINK}
              className="rounded-full border border-[#383838]/20 px-3 py-1 text-[12px] font-semibold text-[#383838] transition-colors hover:bg-[#383838]/10"
            >
              Editar
            </Link>
          </div>
          {isLoadingMonitorados ? (
            <div className="flex items-center justify-center py-8 gap-2 text-[#383838]/60">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span>Carregando...</span>
            </div>
          ) : favoritesQuery.isError ? (
            <div className="py-4 text-sm text-destructive">
              <p>{monitoradosErrorMessage}</p>
              {favoritesQuery.error instanceof ApiError && favoritesQuery.error.status === 401 && (
                <p className="mt-1 text-[#383838]/80">Faça login para ver os parlamentares que você monitora.</p>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-[27px] md:flex-row md:flex-wrap">
              {monitorados.map((parlamentar) => (
                <Link
                  key={parlamentar.id}
                  to={`/parlamentar/${parlamentar.id}`}
                  className="flex min-w-0 w-full items-center gap-3 rounded-[28px] bg-white px-4 py-3 shadow-[0_4px_4px_rgba(0,0,0,0.25)] transition-[transform,background-color] duration-200 ease-out hover:-translate-y-1 hover:bg-[#f9f9f9] md:w-auto md:min-w-[200px]"
                >
                  <Avatar className="h-[50px] w-[50px] shrink-0">
                    <AvatarImage src={parlamentar.foto} alt={parlamentar.nome} />
                    <AvatarFallback>{parlamentar.nome[0]}</AvatarFallback>
                  </Avatar>
                  <div>
                    <p className="font-semibold text-[18px] text-[#383838]">{parlamentar.nome}</p>
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold text-white ${
                          parlamentar.casa === 'camara' ? 'bg-[#1b76ff]' : 'bg-[#09e03b]'
                        }`}
                      >
                        {parlamentar.casa === 'camara' ? 'CÂMARA' : 'SENADO'}
                      </span>
                      <span className="text-[11px] text-[#383838]">
                        {parlamentar.partido.sigla} - {parlamentar.uf}
                      </span>
                    </div>
                  </div>
                </Link>
              ))}
              {monitorados.length === 0 && (
                <p className="text-sm text-[#383838]/60 py-4">Nenhum parlamentar monitorado.</p>
              )}
            </div>
          )}
        </div>

        {/* Main grid: Timeline + Últimas ações */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Linha do tempo — 2 cols */}
          <div className="mp-card lg:col-span-2 bg-white p-6">
            <h2 className="mb-4 truncate text-[32px] leading-none font-bold text-[#090909]">Linha do tempo</h2>
            <div className="h-[560px]">
              <Timeline
                propositions={dashboardActivity?.propositions ?? []}
                votes={dashboardActivity?.votes ?? []}
                isLoading={dashboardActivityQuery.isLoading}
                isError={dashboardActivityQuery.isError}
              />
            </div>
          </div>

          {/* Right column */}
          <div className="space-y-6">
            {/* Últimas ações */}
            <div className="mp-card bg-white p-6">
              <h2 className="mb-4 truncate text-[32px] leading-none font-bold text-[#090909]">Últimas ações</h2>
              <ProposicoesList
                limit={2}
                items={dashboardActivity?.propositions ?? []}
                isLoading={dashboardActivityQuery.isLoading}
                isError={dashboardActivityQuery.isError}
              />
            </div>

          </div>
        </div>
      </main>

      {/* Dashboard footer with congress + mammoth illustration */}
      <div
        ref={footerImageRef}
        className="relative overflow-visible md:overflow-hidden"
        onMouseMove={isMobileViewport ? undefined : handleFooterMouseMove}
        onMouseLeave={isMobileViewport ? undefined : handleFooterMouseLeave}
      >
        <div
          style={{
            transform: isMobileViewport ? 'none' : footerImageTransform,
            transformOrigin: 'center center',
          }}
        >
          <img
            src={banner3}
            alt=""
            style={{
              display: 'block',
              width: '100%',
              height: 'auto',
              marginBottom: isMobileViewport ? '0' : '-250px',
            }}
          />
        </div>
        <div
          className="absolute bottom-5 left-4 right-4 flex flex-col items-start gap-2 sm:left-10 sm:right-10 sm:flex-row sm:items-center sm:justify-between"
          style={{ zIndex: 1 }}
        >
          <img src={logoMamute} alt="Mamute Político" style={{ height: '47px', width: 'auto', filter: 'brightness(0) invert(1)' }} />
          <span className="mp-footer-note text-white" style={{ textShadow: '0 1px 2px rgba(0,0,0,0.5)' }}>
            2026 Mamute Político. Dados obtidos via API aberta do Congresso Nacional.
          </span>
        </div>
      </div>
    </div>
  );
};

export default DashboardPage;
