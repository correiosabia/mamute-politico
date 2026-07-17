import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Parlamentar, CasaLegislativa } from '@/types/parlamentar';
import { getParliamentarianCatalogConfig, listParliamentarians } from '@/api/endpoints';
import type { ParliamentarianSituation } from '@/api/types';
import { mapParliamentarianOutToParlamentar } from '@/api/mappers';
import { ApiError } from '@/api/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { LazyAvatarImage } from '@/components/ui/lazy-avatar-image';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Search, Filter, PlusCircle, X, ExternalLink, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { includesNormalizedSearch, sortByNome } from '@/lib/utils';
import { PLANS_URL } from '@/components/auth/config';

type SituacaoFilter = ParliamentarianSituation;

const SITUACAO_FILTER_LABELS: Record<SituacaoFilter, string> = {
  exercicio: 'Em exercício',
  afastado: 'Afastado',
  licenciado: 'Licenciado',
  fim_de_mandato: 'Fim de mandato',
};

const SAFE_CATALOG_CONFIG = {
  allowed_situations: ['exercicio'],
  default_situacao: 'exercicio',
} as const satisfies {
  allowed_situations: readonly SituacaoFilter[];
  default_situacao: SituacaoFilter;
};

const MONITORADOS_LIMIT_MESSAGE = "Limite atingido. Faça um upgrade do plano em 'Conta'.";
const SELECTION_LIMIT_MESSAGE = 'Limite de parlamentares atingido.';
const LIST_SCROLL_AREA_CLASS =
  'h-full [&_[data-radix-scroll-area-viewport]>div]:!block [&_[data-radix-scroll-area-viewport]>div]:!min-w-0 [&_[data-radix-scroll-area-viewport]>div]:!w-full';

const SITUACAO_FILTER_TO_SITUACAO: Record<
  SituacaoFilter,
  Parlamentar['situacao']
> = {
  exercicio: 'Exercício',
  afastado: 'Afastado',
  licenciado: 'Licenciado',
  fim_de_mandato: 'Fim de mandato',
};

function getSituacaoLabel(situacao: Parlamentar['situacao']): string {
  return situacao === 'Exercício' ? 'Em exercício' : situacao;
}

interface ParlamentarSelectorProps {
  casaSelecionada: CasaLegislativa;
  parlamentaresSelecionados: Parlamentar[];
  onAddParlamentar: (parlamentar: Parlamentar) => void;
  onRemoveParlamentar: (id: string) => void;
  /** When true, shows a loading state in the “Parlamentares monitorados” column. */
  monitoradosLoading?: boolean;
  /** Shown in the monitorados column when favorites failed to load from the API. */
  monitoradosError?: string | null;
  /** Disables add/remove while a favorite mutation is in flight. */
  favoritosMutating?: boolean;
  /** Maximum number of parliamentarians allowed by the current plan. */
  monitoradosLimit?: number | null;
  /** Number of parliamentarians already using the plan quota. */
  monitoradosUsed?: number | null;
  /** Shows a neutral quota state while the plan limit is loading. */
  monitoradosQuotaLoading?: boolean;
  /** Parliamentarian whose favorite mutation most recently succeeded. */
  recentlyAdded?: Parlamentar | null;
}

export function ParlamentarSelector({
  casaSelecionada,
  parlamentaresSelecionados,
  onAddParlamentar,
  onRemoveParlamentar,
  monitoradosLoading = false,
  monitoradosError = null,
  favoritosMutating = false,
  monitoradosLimit = null,
  monitoradosUsed = null,
  monitoradosQuotaLoading = false,
  recentlyAdded = null,
}: ParlamentarSelectorProps) {
  const navigate = useNavigate();
  const monitoradosCardRef = useRef<HTMLDivElement>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [partidoFilter, setPartidoFilter] = useState<string>('todos');
  const [ufFilter, setUfFilter] = useState<string>('todos');
  const [legislaturaFilter, setLegislaturaFilter] = useState<string>('todos');
  const [situacaoFilter, setSituacaoFilter] = useState<SituacaoFilter>('exercicio');
  const hasAppliedCatalogDefault = useRef(false);

  const {
    data: catalogConfig,
    isLoading: catalogConfigLoading,
    isError: catalogConfigError,
  } = useQuery({
    queryKey: ['parliamentarian-catalog-config'],
    queryFn: getParliamentarianCatalogConfig,
  });
  const hasValidCatalogConfig = Boolean(
    catalogConfig &&
    catalogConfig.allowed_situations.length > 0 &&
    catalogConfig.allowed_situations.includes(catalogConfig.default_situacao),
  );
  const effectiveCatalogConfig =
    catalogConfig && hasValidCatalogConfig ? catalogConfig : SAFE_CATALOG_CONFIG;
  const allowedSituacoes = effectiveCatalogConfig.allowed_situations;
  const defaultSituacao = effectiveCatalogConfig.default_situacao;
  const waitingForCatalogDefault = hasValidCatalogConfig && !hasAppliedCatalogDefault.current;

  useEffect(() => {
    if (!hasValidCatalogConfig || hasAppliedCatalogDefault.current) return;

    hasAppliedCatalogDefault.current = true;
    setSituacaoFilter(defaultSituacao);
  }, [defaultSituacao, hasValidCatalogConfig]);

  const selectedSituacao = allowedSituacoes.includes(situacaoFilter)
    ? situacaoFilter
    : defaultSituacao;

  const typeFilter = useMemo<Array<'deputado' | 'senado'>>(() => {
    if (casaSelecionada === 'camara') return ['deputado'];
    if (casaSelecionada === 'senado') return ['senado'];
    return ['deputado', 'senado'];
  }, [casaSelecionada]);

  const {
    data: rawList,
    isLoading: parliamentariansLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['parliamentarians', partidoFilter, typeFilter.join(','), selectedSituacao],
    queryFn: () =>
      listParliamentarians({
        limit: 1000,
        offset: 0,
        party: partidoFilter !== 'todos' ? partidoFilter : undefined,
        type: typeFilter,
        situacao: selectedSituacao,
      }),
    enabled: !catalogConfigLoading && !waitingForCatalogDefault,
  });
  const isLoading = catalogConfigLoading || parliamentariansLoading;

  const allParlamentares = useMemo(() => {
    if (!rawList) return [];
    return rawList.map(mapParliamentarianOutToParlamentar);
  }, [rawList]);

  const parlamentaresDisponiveis = useMemo(() => {
    const filtered = allParlamentares.filter((p) => {
      // Filter by search term
      if (searchTerm && !includesNormalizedSearch(p.nome, searchTerm)) {
        return false;
      }

      // Filter by partido (already applied in API when partidoFilter !== 'todos')
      if (partidoFilter !== 'todos' && p.partido.sigla !== partidoFilter) {
        return false;
      }

      // Filter by UF
      if (ufFilter !== 'todos' && p.uf !== ufFilter) {
        return false;
      }

      // Filter by legislatura
      if (legislaturaFilter !== 'todos' && p.legislatura !== Number(legislaturaFilter)) {
        return false;
      }

      // Keep the rendered records consistent with the server-selected situation.
      if (p.situacao !== SITUACAO_FILTER_TO_SITUACAO[selectedSituacao]) {
        return false;
      }

      // Exclude already selected
      if (parlamentaresSelecionados.find((s) => s.id === p.id)) {
        return false;
      }

      return true;
    });
    return sortByNome(filtered);
  }, [allParlamentares, searchTerm, partidoFilter, ufFilter, legislaturaFilter, selectedSituacao, parlamentaresSelecionados]);

  const parlamentaresSelecionadosOrdenados = useMemo(
    () => sortByNome(parlamentaresSelecionados),
    [parlamentaresSelecionados],
  );
  const quotaUsed =
    typeof monitoradosUsed === 'number' ? monitoradosUsed : parlamentaresSelecionados.length;
  const monitoradosLimitReached =
    typeof monitoradosLimit === 'number' &&
    quotaUsed >= monitoradosLimit;
  const canAddParlamentar = !favoritosMutating && !monitoradosLimitReached;
  const quotaLabel =
    typeof monitoradosLimit === 'number'
      ? `${quotaUsed}/${monitoradosLimit}`
      : monitoradosQuotaLoading
        ? '...'
        : `+${parlamentaresSelecionados.length}`;

  const partidosOptions = useMemo(() => {
    const siglas = new Set((rawList ?? []).map((p) => p.party).filter(Boolean) as string[]);
    return Array.from(siglas).sort();
  }, [rawList]);

  const estadosOptions = useMemo(() => {
    const ufs = new Set(allParlamentares.map((p) => p.uf).filter(Boolean));
    return Array.from(ufs).sort();
  }, [allParlamentares]);

  const legislaturasOptions = useMemo(() => {
    const nums = new Set(allParlamentares.map((p) => p.legislatura));
    return Array.from(nums).sort((a, b) => b - a);
  }, [allParlamentares]);

  const clearFilters = () => {
    setSearchTerm('');
    setPartidoFilter('todos');
    setUfFilter('todos');
    setLegislaturaFilter('todos');
    setSituacaoFilter(defaultSituacao);
  };

  const focusMonitorados = () => {
    monitoradosCardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    monitoradosCardRef.current?.focus({ preventScroll: true });
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      {/* Available Parliamentarians */}
      <Card className="mp-card flex h-[564px] flex-col border-none bg-white">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-[32px] leading-none font-bold text-[#090909]">Parlamentares disponíveis</CardTitle>
            <Badge variant="secondary" className="bg-transparent text-[18px] font-medium text-[#7f7c7c]">+{parlamentaresDisponiveis.length}</Badge>
          </div>

          {monitoradosLimitReached && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-[#ff0004]/5 px-3 py-2 text-sm text-[#393939]">
              <span>Você atingiu o limite do seu plano.</span>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" size="sm" onClick={focusMonitorados}>
                  Remover um monitorado
                </Button>
                <a
                  href={PLANS_URL}
                  className="inline-flex min-h-9 items-center rounded-full bg-[#ff0004] px-4 text-xs font-semibold text-white no-underline transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff0004] focus-visible:ring-offset-2"
                >
                  Ver planos
                </a>
              </div>
            </div>
          )}

          {recentlyAdded && (
            <div role="status" className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-[#09e03b]/10 px-3 py-2 text-sm text-[#116b25]">
              <span><strong>{recentlyAdded.nome}</strong> foi adicionado aos monitorados.</span>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" size="sm" onClick={focusMonitorados}>
                  Ver monitorados
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => navigate(`/parlamentar/${recentlyAdded.id}`)}>
                  Abrir perfil
                </Button>
              </div>
            </div>
          )}
          
          {/* Search and Filters */}
          <div className="space-y-3 pt-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar por nome..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="h-9 rounded-[76px] border-none bg-[#efeeee] pl-9"
              />
            </div>
            {catalogConfigError && (
              <p role="status" className="text-sm text-muted-foreground">
                Não foi possível carregar as opções do catálogo. Mostrando parlamentares em
                exercício.
              </p>
            )}
            
            <div className="flex gap-2 flex-wrap">
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-2">
                    <Filter className="h-3.5 w-3.5" />
                    Filtros
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-80 bg-popover" align="start">
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Situação</label>
                      <Select
                        value={selectedSituacao}
                        onValueChange={(value) => setSituacaoFilter(value as SituacaoFilter)}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Em exercício" />
                        </SelectTrigger>
                        <SelectContent className="bg-popover">
                          {allowedSituacoes.map((key) => (
                            <SelectItem key={key} value={key}>
                              {SITUACAO_FILTER_LABELS[key]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <label className="text-sm font-medium">Partido</label>
                      <Select value={partidoFilter} onValueChange={setPartidoFilter}>
                        <SelectTrigger>
                          <SelectValue placeholder="Todos os partidos" />
                        </SelectTrigger>
                        <SelectContent className="bg-popover">
                          <SelectItem value="todos">Todos os partidos</SelectItem>
                          {partidosOptions.map((sigla) => (
                            <SelectItem key={sigla} value={sigla}>
                              {sigla}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Estado (UF)</label>
                      <Select value={ufFilter} onValueChange={setUfFilter}>
                        <SelectTrigger>
                          <SelectValue placeholder="Todos os estados" />
                        </SelectTrigger>
                        <SelectContent className="bg-popover max-h-60">
                          <SelectItem value="todos">Todos os estados</SelectItem>
                          {estadosOptions.map((uf) => (
                            <SelectItem key={uf} value={uf}>
                              {uf}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Legislatura</label>
                      <Select value={legislaturaFilter} onValueChange={setLegislaturaFilter}>
                        <SelectTrigger>
                          <SelectValue placeholder="Todas as legislaturas" />
                        </SelectTrigger>
                        <SelectContent className="bg-popover">
                          <SelectItem value="todos">Todas as legislaturas</SelectItem>
                          {legislaturasOptions.map((numero) => (
                            <SelectItem key={numero} value={String(numero)}>
                              {numero}ª
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    
                    <Button variant="ghost" size="sm" onClick={clearFilters} className="w-full">
                      Limpar filtros
                    </Button>
                  </div>
                </PopoverContent>
              </Popover>

              {/* Active filter badges */}
              {selectedSituacao !== defaultSituacao && (
                <Badge variant="secondary" className="gap-1">
                  {SITUACAO_FILTER_LABELS[selectedSituacao]}
                  <X className="h-3 w-3 cursor-pointer" onClick={() => setSituacaoFilter(defaultSituacao)} />
                </Badge>
              )}
              {partidoFilter !== 'todos' && (
                <Badge variant="secondary" className="gap-1">
                  {partidoFilter}
                  <X className="h-3 w-3 cursor-pointer" onClick={() => setPartidoFilter('todos')} />
                </Badge>
              )}
              {ufFilter !== 'todos' && (
                <Badge variant="secondary" className="gap-1">
                  {ufFilter}
                  <X className="h-3 w-3 cursor-pointer" onClick={() => setUfFilter('todos')} />
                </Badge>
              )}
              {legislaturaFilter !== 'todos' && (
                <Badge variant="secondary" className="gap-1">
                  {legislaturaFilter}ª Leg.
                  <X className="h-3 w-3 cursor-pointer" onClick={() => setLegislaturaFilter('todos')} />
                </Badge>
              )}
            </div>
          </div>
        </CardHeader>
        
        <CardContent className="flex-1 overflow-hidden">
          <ScrollArea className={LIST_SCROLL_AREA_CLASS}>
            {isLoading && (
              <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>Carregando parlamentares...</span>
              </div>
            )}
            {isError && (
              <div className="text-center py-8 text-destructive">
                <p>Falha ao carregar parlamentares.</p>
                <p className="text-sm mt-1">
                  {error instanceof ApiError && error.status === 401
                    ? 'Token ausente ou expirado. Faça login para continuar.'
                    : error instanceof Error ? error.message : 'Tente novamente.'}
                </p>
              </div>
            )}
            {!isLoading && !isError && (
              <TooltipProvider delayDuration={0} skipDelayDuration={0}>
                <div className="flex flex-col gap-2 pr-4">
                  {parlamentaresDisponiveis.map((parlamentar) => {
                    const addButton = (
                      <button
                        type="button"
                        disabled={!canAddParlamentar}
                        onClick={() => onAddParlamentar(parlamentar)}
                        aria-label={
                          monitoradosLimitReached
                            ? `Limite do plano atingido para ${parlamentar.nome}`
                            : `Adicionar ${parlamentar.nome} aos parlamentares monitorados`
                        }
                        className="group flex min-h-[72px] min-w-0 w-full items-center justify-between rounded-lg border bg-card p-3 text-left transition-colors hover:bg-muted/50 active:bg-muted/70 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <div className="flex min-w-0 items-center gap-3">
                          <LazyAvatarImage
                            className="h-10 w-10"
                            src={parlamentar.foto}
                            alt={parlamentar.nome}
                            fallback={parlamentar.nome[0]}
                          />
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium">{parlamentar.nome}</p>
                            <div className="flex items-center gap-2 flex-wrap">
                              <Badge variant={parlamentar.casa === 'camara' ? 'camara' : 'senado'} className="text-[10px] px-1.5 py-0">
                                {parlamentar.casa === 'camara' ? 'Câmara' : 'Senado'}
                              </Badge>
                              <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                                {getSituacaoLabel(parlamentar.situacao)}
                              </Badge>
                              <span className="text-xs text-muted-foreground">
                                {parlamentar.partido.sigla} - {parlamentar.uf}
                              </span>
                            </div>
                          </div>
                        </div>
                        <span
                          aria-hidden="true"
                          className="ml-3 inline-flex min-h-10 shrink-0 items-center gap-1 rounded-full bg-[#09e03b]/10 px-3 text-xs font-semibold text-[#116b25] transition-colors group-hover:bg-[#09e03b]/20 group-disabled:bg-muted group-disabled:text-muted-foreground"
                        >
                          <PlusCircle className="h-4 w-4" />
                          <span>{monitoradosLimitReached ? 'Limite' : 'Adicionar'}</span>
                        </span>
                      </button>
                    );

                    if (!monitoradosLimitReached) {
                      return <Fragment key={parlamentar.id}>{addButton}</Fragment>;
                    }

                    return (
                      <Tooltip key={parlamentar.id}>
                        <TooltipTrigger asChild>
                          <span className="block min-w-0 w-full cursor-not-allowed">
                            {addButton}
                          </span>
                        </TooltipTrigger>
                        <TooltipContent
                          data-testid="plan-limit-tooltip-content"
                          side="top"
                          align="end"
                          collisionPadding={16}
                          className="pointer-events-auto flex max-w-[calc(100vw-2rem)] flex-col items-start gap-2 text-balance p-3 sm:max-w-64"
                        >
                          <span>{SELECTION_LIMIT_MESSAGE}</span>
                          <a
                            href={PLANS_URL}
                            className="inline-flex min-h-9 items-center rounded-full bg-[#ff0004] px-4 text-xs font-semibold text-white no-underline transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff0004] focus-visible:ring-offset-2"
                          >
                            Fazer upgrade
                          </a>
                        </TooltipContent>
                      </Tooltip>
                    );
                  })}
                  {parlamentaresDisponiveis.length === 0 && (
                    <div className="text-center py-8 text-muted-foreground">
                      <p>Nenhum parlamentar encontrado com os filtros selecionados.</p>
                    </div>
                  )}
                </div>
              </TooltipProvider>
            )}
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Selected Parliamentarians */}
      <Card ref={monitoradosCardRef} tabIndex={-1} className="mp-card flex h-[564px] flex-col border-none bg-white">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-[32px] leading-none font-bold text-[#090909]">Parlamentares monitorados</CardTitle>
            <Badge variant="secondary" className="min-w-14 justify-center bg-transparent text-[18px] font-medium text-[#7f7c7c]">{quotaLabel}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {monitoradosLimitReached
              ? MONITORADOS_LIMIT_MESSAGE
              : 'Clique no parlamentar para acessar seu dashboard completo'}
          </p>
        </CardHeader>
        
        <CardContent className="flex-1 overflow-hidden">
          <ScrollArea className={LIST_SCROLL_AREA_CLASS}>
            {monitoradosLoading ? (
              <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>Carregando favoritos...</span>
              </div>
            ) : monitoradosError ? (
              <div className="text-center py-8 text-destructive">
                <p>{monitoradosError}</p>
              </div>
            ) : (
            <div className="flex flex-col gap-2 pr-4">
              {parlamentaresSelecionadosOrdenados.map((parlamentar) => (
                <div
                  key={parlamentar.id}
                  className="flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-accent/5 transition-colors group cursor-pointer"
                  onClick={() => navigate(`/parlamentar/${parlamentar.id}`)}
                >
                  <div className="flex items-center gap-3">
                    <Avatar className="h-10 w-10">
                      <AvatarImage src={parlamentar.foto} alt={parlamentar.nome} />
                      <AvatarFallback>{parlamentar.nome[0]}</AvatarFallback>
                    </Avatar>
                    <div>
                      <p className="font-medium text-sm">{parlamentar.nome}</p>
                      <div className="flex items-center gap-2">
                        <Badge variant={parlamentar.casa === 'camara' ? 'camara' : 'senado'} className="text-[10px] px-1.5 py-0">
                          {parlamentar.casa === 'camara' ? 'Câmara' : 'Senado'}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {parlamentar.partido.sigla} - {parlamentar.uf}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={favoritosMutating}
                      className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-foreground"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/parlamentar/${parlamentar.id}`);
                      }}
                      aria-label={`Abrir perfil de ${parlamentar.nome}`}
                    >
                      <ExternalLink className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={favoritosMutating}
                      className="text-destructive hover:text-destructive hover:bg-destructive/10"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRemoveParlamentar(parlamentar.id);
                      }}
                      aria-label={`Remover ${parlamentar.nome} dos parlamentares monitorados`}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
              {parlamentaresSelecionados.length === 0 && (
                <div className="text-center py-8 text-muted-foreground">
                  <p>Nenhum parlamentar selecionado ainda.</p>
                  <p className="text-sm mt-1">Adicione parlamentares da lista ao lado.</p>
                </div>
              )}
            </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
