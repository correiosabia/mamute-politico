import { useParams, Link } from 'react-router-dom';
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
import { getParliamentarian } from '@/api/endpoints';
import { mapParliamentarianOutToParlamentar } from '@/api/mappers';
import { ApiError } from '@/api/client';
import { ArrowLeft, Cloud, FileText, Vote, Loader2 } from 'lucide-react';

const parlamentarSectionTabTriggerClass =
  'rounded-full border-0 px-6 py-2.5 text-[13px] font-semibold uppercase tracking-wide text-[#090909] shadow-none ring-offset-0 transition-all focus-visible:ring-2 focus-visible:ring-black/25 focus-visible:ring-offset-0 data-[state=active]:bg-[#090909] data-[state=active]:text-white data-[state=active]:shadow-none data-[state=inactive]:bg-[#f5f5f5] data-[state=inactive]:text-[#090909] data-[state=inactive]:shadow-[0_2px_8px_rgba(0,0,0,0.12)]';

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
  const numericId = id != null ? Number(id) : NaN;
  const isIdValid = Number.isInteger(numericId) && numericId > 0;

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

  return (
    <div className="min-h-screen bg-textura-gold">
      <Header />

      <main className="container py-8 space-y-6">
        {/* Back button */}
        <Link to="/dashboard">
          <button className="flex items-center gap-2 rounded-[76px] bg-white px-5 py-2 text-[13px] font-semibold text-[#383838] shadow-sm transition hover:opacity-90">
            <ArrowLeft className="h-4 w-4" />
            VOLTAR AO DASHBOARD GERAL
          </button>
        </Link>

        {/* Top Row: Dados cadastrais | Temas do discurso | Últimos projetos */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Dados cadastrais */}
          <div className="mp-card bg-white p-6">
            <h2 className="mb-4 text-[32px] font-bold text-[#090909]">Dados cadastrais</h2>
            <ParlamentarInfo parlamentar={parlamentar} />
          </div>

          {/* Temas do discurso */}
          <div className="mp-card bg-white p-6">
            <h2 className="mb-4 text-[32px] font-bold text-[#090909]">Temas do discurso</h2>
            <WordCloud parliamentarianId={parliamentarianCode} parlamentarNome={parlamentar.nome} />
          </div>

          {/* Últimos projetos */}
          <div className="mp-card bg-white p-6">
            <h2 className="mb-4 text-[32px] font-bold text-[#090909]">Últimos projetos</h2>
            <ProposicoesList limit={4} parliamentarianId={id} />
          </div>
        </div>

        {/* Bottom: Proposições do Parlamentar with tabs */}
        <div className="mp-card bg-white">
          <Tabs defaultValue="votacoes" className="w-full">
            <div className="flex flex-col gap-4 border-b border-black/[0.06] px-6 pt-6 pb-4">
              <TabsList className="inline-flex h-auto w-fit max-w-full shrink-0 flex-wrap items-center gap-2 bg-transparent p-0">
                <TabsTrigger value="votacoes" className={parlamentarSectionTabTriggerClass}>
                  VOTAÇÕES
                </TabsTrigger>
                <TabsTrigger value="proposicoes" className={parlamentarSectionTabTriggerClass}>
                  PROPOSIÇÕES
                </TabsTrigger>
                <TabsTrigger value="taquigraficas" className={parlamentarSectionTabTriggerClass}>
                  TAQUIGRÁFICAS
                </TabsTrigger>
              </TabsList>
              <h2 className="text-[32px] font-bold text-[#090909]">Atividades do Parlamentar</h2>
            </div>
            <TabsContent value="votacoes" className="mt-0 p-6 pt-4 h-[500px]">
              <VotacoesTable parliamentarianId={numericId} />
            </TabsContent>
            <TabsContent value="proposicoes" className="mt-0 p-6 pt-4">
              <ProposicoesTable parliamentarianId={id} />
            </TabsContent>
            <TabsContent value="taquigraficas" className="mt-0 p-6 pt-4 h-[500px]">
              <TaquigraficasTable parliamentarianId={numericId} />
            </TabsContent>
          </Tabs>
        </div>
      </main>
      <SelecaoFooter />
    </div>
  );
};

export default ParlamentarDashboard;
