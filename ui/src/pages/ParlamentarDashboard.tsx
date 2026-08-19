import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/Header';
import { SelecaoFooter } from '@/components/selecao/SelecaoFooter';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ParlamentarInfo } from '@/components/dashboard/ParlamentarInfo';
import { WordCloud } from '@/components/dashboard/WordCloud';
import { ProposicoesList } from '@/components/dashboard/ProposicoesList';
import { ProposicoesTable } from '@/components/dashboard/ProposicoesTable';
import { VotacoesTable } from '@/components/dashboard/VotacoesTable';
import { TaquigraficasTable } from '@/components/dashboard/TaquigraficasTable';
import { EmendasTable } from '@/components/dashboard/EmendasTable';
import { GastosTab } from '@/components/dashboard/GastosTab';
import { TrajetoriaTab } from '@/components/dashboard/TrajetoriaTab';
import { PaywallOverlay } from '@/components/paywall/PaywallOverlay';
import { useFeatureAccess } from '@/hooks/useFeatureAccess';
import { useMarcacoesPessoais } from '@/hooks/useMarcacoesPessoais';
import { MarcacoesInline } from '@/components/marcacoes/MarcacoesInline';
import { EstatisticasCard } from '@/components/dashboard/EstatisticasCard';
import { TrackSection } from '@/components/TrackSection';
import { sendSectionView } from '@/api/events';
import {
  getAmendmentsSummary,
  getMyParliamentarianDashboardStats,
  getParliamentarian,
  listMyProjectFavorites,
} from '@/api/endpoints';
import { mapParliamentarianOutToParlamentar } from '@/api/mappers';
import { ApiError } from '@/api/client';
import { ArrowLeft, Cloud, FileText, Vote, Loader2, Lock, Users, Pencil } from 'lucide-react';

const MONITORADOS_AMBAS_CASAS_LINK = '/selecao#ambas-casas';

const parlamentarSectionTabTriggerClass =
  'shrink-0 rounded-full border-0 px-6 py-2.5 text-[13px] font-semibold uppercase tracking-wide text-[#090909] shadow-none ring-offset-0 transition-all focus-visible:ring-2 focus-visible:ring-black/25 focus-visible:ring-offset-0 data-[state=active]:bg-[#090909] data-[state=active]:text-white data-[state=active]:shadow-none data-[state=inactive]:bg-[#f5f5f5] data-[state=inactive]:text-[#090909] data-[state=inactive]:shadow-[0_2px_8px_rgba(0,0,0,0.12)]';

const toErrorMessage = (value: unknown): string => {
  if (value instanceof Error) {
    if (value.message && value.message !== '[object Object]') return value.message;
    const maybeResponseData = (value as Error & { response?: { data?: unknown } }).response?.data;
    if (maybeResponseData != null && typeof maybeResponseData === 'object') {
      const detail = (maybeResponseData as { detail?: unknown }).detail;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail) && detail.length > 0 && typeof detail[0] === 'string') {
        return detail[0];
      }
    }
    return 'Falha ao carregar dados do parlamentar.';
  }
  if (typeof value === 'string') return value;
  if (value != null && typeof value === 'object') {
    const maybeMessage = (value as { message?: unknown }).message;
    if (typeof maybeMessage === 'string') return maybeMessage;
    try {
      return JSON.stringify(value);
    } catch {
      return 'Falha ao carregar dados do parlamentar.';
    }
  }
  return 'Falha ao carregar dados do parlamentar.';
};

const ParlamentarDashboard = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const numericId = id != null ? Number(id) : NaN;
  const isIdValid = Number.isInteger(numericId) && numericId > 0;
  // Gerenciadas em /admin/configuracoes (estado) e na tela de Planos (modo
  // por plano: oculto/cadeado/liberado). 'bloqueada' monta a aba com cadeado
  // e a previa desfocada (CS-58). Para remover a flag, ver o procedimento em
  // `@/lib/featureFlags`.
  const emendasAccess = useFeatureAccess('emendas');
  const trajetoriaAccess = useFeatureAccess('trajetoria');
  const cotaAccess = useFeatureAccess('cota_parlamentar');

  const { data: raw, isLoading, isError, error } = useQuery({
    queryKey: ['parliamentarian', id],
    queryFn: () => getParliamentarian(numericId),
    enabled: isIdValid,
  });

  const parlamentar = raw != null ? mapParliamentarianOutToParlamentar(raw) : null;
  const parliamentarianCode =
    raw?.parliamentarian_code != null && raw.parliamentarian_code > 0
      ? raw.parliamentarian_code
      : numericId;
  const favoritesQuery = useQuery({
    queryKey: ['project-favorites', 'me'],
    queryFn: () => listMyProjectFavorites(),
  });
  const dashboardStatsQuery = useQuery({
    queryKey: ['dashboard-stats', 'parliamentarian', numericId],
    queryFn: () => getMyParliamentarianDashboardStats(numericId),
    enabled: isIdValid,
  });
  // Emendas sao grandeza de ano civil, diferente do dashboardStats (3 meses),
  // por isso query e endpoint proprios. So busca com acesso pleno: bloqueado,
  // o card mostra o cadeado sem tocar a API (a rota devolveria 403).
  const emendasYear = new Date().getFullYear();
  const amendmentsSummaryQuery = useQuery({
    queryKey: ['amendments-summary', numericId, emendasYear],
    queryFn: () => getAmendmentsSummary(numericId, emendasYear),
    enabled: isIdValid && emendasAccess === 'liberada',
  });
  const monitoradosCount = favoritesQuery.data?.length ?? 0;
  const monitorado =
    favoritesQuery.data?.some((f) => f.parliamentarian_id === numericId) ?? false;
  // Mesmo hook da Seleção e do Dashboard: flag global e plano já resolvidos.
  const { tagsPessoais, mamutometro } = useMarcacoesPessoais({ enabled: isIdValid });

  if (!isIdValid) {
    return (
      <div className="min-h-screen bg-textura-gold">
        <Header />
        <main className="container py-8">
          <div className="mx-auto max-w-xl rounded-[28px] border border-black/10 bg-white p-8 text-center shadow-md">
            <h1 className="mb-3 text-4xl font-bold text-[#1f2b44]">Parlamentar não encontrado</h1>
            <p className="mb-6 text-base text-muted-foreground">O identificador informado não é válido para esta rota.</p>
            <Link to="/selecao">
              <Button variant="hero" className="px-8">Voltar à seleção</Button>
            </Link>
          </div>
        </main>
        <SelecaoFooter />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-textura-gold">
        <Header />
        <main className="container py-8">
          <div className="mx-auto flex max-w-xl items-center justify-center gap-3 rounded-[28px] border border-black/10 bg-white p-8 text-muted-foreground shadow-md">
            <Loader2 className="h-6 w-6 animate-spin" />
            <span className="text-lg font-medium">Carregando parlamentar...</span>
          </div>
        </main>
        <SelecaoFooter />
      </div>
    );
  }

  if (isError || !parlamentar) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="min-h-screen bg-textura-gold">
        <Header />
        <main className="container py-8">
          <div className="mx-auto max-w-xl rounded-[28px] border border-black/10 bg-white p-8 text-center shadow-md">
            <h1 className="mb-3 text-5xl font-bold text-[#1f2b44]">
              {notFound ? 'Parlamentar não encontrado' : 'Falha ao carregar'}
            </h1>
            {!notFound && (
              <p className="mb-6 text-base text-muted-foreground">
                {toErrorMessage(error)}
              </p>
            )}
            <Link to="/selecao">
              <Button variant="hero" className="px-8">Voltar à seleção</Button>
            </Link>
          </div>
        </main>
        <SelecaoFooter />
      </div>
    );
  }

  // Abas derivadas de uma lista: o portão da flag fica em UM lugar só. Antes
  // eram duas condições espalhadas (TabsTrigger e TabsContent), e é esse tipo
  // de espalhamento que torna caro remover a flag depois. Aba 'locked' fica
  // na lista em cinza com cadeado; o conteúdo monta o componente real (que já
  // recebe a prévia truncada do backend) sob o desfoque com CTA.
  const abas = [
    {
      value: 'votacoes',
      locked: false,
      label: 'VOTAÇÕES',
      className: 'mt-0 p-6 pt-4 h-[500px]',
      content: <VotacoesTable parliamentarianId={numericId} />,
    },
    {
      value: 'proposicoes',
      locked: false,
      label: 'PROPOSIÇÕES',
      className: 'mt-0 p-6 pt-4',
      content: <ProposicoesTable parliamentarianId={id} />,
    },
    {
      value: 'taquigraficas',
      locked: false,
      label: 'TAQUIGRÁFICAS',
      className: 'mt-0 p-6 pt-4 h-[500px]',
      content: <TaquigraficasTable parliamentarianId={numericId} />,
    },
    ...(emendasAccess !== 'oculta'
      ? [
          {
            value: 'emendas',
            label: 'EMENDAS',
            locked: emendasAccess === 'bloqueada',
            className: 'mt-0 p-6 pt-4 h-[500px]',
            content:
              emendasAccess === 'bloqueada' ? (
                <PaywallOverlay recurso="a aba Emendas">
                  <EmendasTable parliamentarianId={numericId} year={emendasYear} />
                </PaywallOverlay>
              ) : (
                <EmendasTable parliamentarianId={numericId} year={emendasYear} />
              ),
          },
        ]
      : []),
    ...(cotaAccess !== 'oculta'
      ? [
          {
            value: 'gastos',
            label: 'GASTOS',
            locked: cotaAccess === 'bloqueada',
            className: 'mt-0 p-6 pt-4 h-[500px]',
            content:
              cotaAccess === 'bloqueada' ? (
                <PaywallOverlay recurso="a aba Gastos">
                  <GastosTab parliamentarianId={numericId} />
                </PaywallOverlay>
              ) : (
                <GastosTab parliamentarianId={numericId} />
              ),
          },
        ]
      : []),
    ...(trajetoriaAccess !== 'oculta'
      ? [
          {
            value: 'trajetoria',
            label: 'TRAJETÓRIA',
            locked: trajetoriaAccess === 'bloqueada',
            className: 'mt-0 p-6 pt-4 h-[500px]',
            content:
              trajetoriaAccess === 'bloqueada' ? (
                <PaywallOverlay recurso="a aba Trajetória">
                  <TrajetoriaTab parliamentarianId={numericId} />
                </PaywallOverlay>
              ) : (
                <TrajetoriaTab parliamentarianId={numericId} />
              ),
          },
        ]
      : []),
  ];

  return (
    <div className="min-h-screen bg-textura-gold">
      <Header />

      <main className="container py-8 space-y-6">
        {/* Top action buttons */}
        <div className="flex flex-wrap items-center justify-center gap-[16px] md:justify-between">
          <button
            type="button"
            onClick={() => navigate('/dashboard')}
            className="flex items-center min-w-[295px] gap-2 rounded-[76px] bg-white px-6 py-2 text-[13px] font-semibold text-[#383838] shadow-sm transition hover:opacity-90"
          >
            <ArrowLeft className="h-4 w-4" />
            VOLTAR AO DASHBOARD GERAL
          </button>
          <Link
            to={MONITORADOS_AMBAS_CASAS_LINK}
            className="group flex items-center min-w-[295px] gap-2 rounded-[76px] bg-[#1b76ff] px-6 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:opacity-90"
          >
            <span className="relative inline-flex h-4 w-4 shrink-0 items-center justify-center">
              <Users className="h-4 w-4 transition-opacity duration-150 group-hover:opacity-0" />
              <Pencil className="absolute h-4 w-4 opacity-0 transition-opacity duration-150 group-hover:opacity-100" />
            </span>
            {monitoradosCount} PARLAMENTAR{monitoradosCount !== 1 ? 'ES' : ''} MONITORADO{monitoradosCount !== 1 ? 'S' : ''}
          </Link>
        </div>

        {/* Top Row: Coluna 1 (Dados cadastrais + Estatísticas) | Temas do discurso | Últimas ações */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Coluna 1: Dados cadastrais + Estatísticas */}
          <div className="flex flex-col gap-6">
            <div className="mp-card bg-white p-6">
              <h2 className="mb-4 text-[32px] leading-none font-bold text-[#090909]">Dados cadastrais</h2>
              <ParlamentarInfo parlamentar={parlamentar} />
              {/* Marcações pessoais do assinante sobre ESTE parlamentar — dado
                  privado do projeto, por isso apartado do cadastro público pelo
                  divider + rótulo. Some por inteiro (rótulo incluso) com as
                  flags/plano desligados ou com o político fora do escopo
                  configurado (ex.: mamutômetro em `monitorados` num perfil não
                  monitorado). */}
              <MarcacoesInline
                titulo="Suas marcações"
                parlamentarId={String(numericId)}
                parlamentarNome={parlamentar.nome}
                monitorado={monitorado}
                tagsPessoais={tagsPessoais}
                mamutometro={mamutometro}
              />
            </div>

            <EstatisticasCard
              stats={dashboardStatsQuery.data}
              isLoading={dashboardStatsQuery.isLoading}
              amendmentsSummary={amendmentsSummaryQuery.data}
              amendmentsYear={emendasYear}
              emendasBloqueadas={emendasAccess === 'bloqueada'}
            />
          </div>

          {/* Temas do discurso */}
          <TrackSection page="parlamentar" section="temas-discurso" className="mp-card bg-white p-6">
            <h2 className="mb-4 text-[32px] leading-none font-bold text-[#090909]">Temas do discurso</h2>
            <WordCloud
              parliamentarianCode={parliamentarianCode}
              parliamentarianId={numericId}
              parlamentarNome={parlamentar.nome}
            />
          </TrackSection>

          {/* Últimas ações */}
          <TrackSection page="parlamentar" section="ultimas-acoes" className="mp-card bg-white p-6">
            <h2 className="mb-4 text-[32px] leading-none font-bold text-[#090909]">Últimas ações</h2>
            <ProposicoesList limit={4} parliamentarianId={id} />
          </TrackSection>
        </div>

        {/* Bottom: Proposições do Parlamentar with tabs */}
        <TrackSection page="parlamentar" section="atividades" className="mp-card bg-white">
          <Tabs
            defaultValue="votacoes"
            className="w-full"
            onValueChange={(value) => sendSectionView('parlamentar', value)}
          >
            <div className="flex flex-col gap-4 border-b border-black/[0.06] px-6 pt-6 pb-4">
              <div className="-mx-6 w-[calc(100%+3rem)] max-w-none overflow-x-auto overflow-y-visible px-6 [-webkit-overflow-scrolling:touch] [scrollbar-width:thin]">
                <TabsList className="inline-flex h-auto w-max min-w-max shrink-0 flex-nowrap items-center gap-2 bg-transparent p-0">
                  {abas.map((aba) => (
                    <TabsTrigger
                      key={aba.value}
                      value={aba.value}
                      className={`${parlamentarSectionTabTriggerClass}${
                        aba.locked
                          ? ' data-[state=inactive]:text-[#090909]/45 data-[state=active]:bg-[#6b6b6b]'
                          : ''
                      }`}
                    >
                      {aba.locked && (
                        <Lock className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                      )}
                      {aba.label}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </div>
              <h2 className="text-[32px] leading-none font-bold text-[#090909]">Atividades do Parlamentar</h2>
            </div>
            {abas.map((aba) => (
              <TabsContent key={aba.value} value={aba.value} className={aba.className}>
                {aba.content}
              </TabsContent>
            ))}
          </Tabs>
        </TrackSection>
      </main>
      <SelecaoFooter />
    </div>
  );
};

export default ParlamentarDashboard;
