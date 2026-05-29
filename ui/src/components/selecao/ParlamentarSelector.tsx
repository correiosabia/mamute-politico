import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Parlamentar, CasaLegislativa } from '@/types/parlamentar';
import { listParliamentarians } from '@/api/endpoints';
import { mapParliamentarianOutToParlamentar } from '@/api/mappers';
import { ApiError } from '@/api/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
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
import { Search, Filter, PlusCircle, X, ExternalLink, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

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
}

export function ParlamentarSelector({
  casaSelecionada,
  parlamentaresSelecionados,
  onAddParlamentar,
  onRemoveParlamentar,
  monitoradosLoading = false,
  monitoradosError = null,
  favoritosMutating = false,
}: ParlamentarSelectorProps) {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const [partidoFilter, setPartidoFilter] = useState<string>('todos');
  const [ufFilter, setUfFilter] = useState<string>('todos');
  const [legislaturaFilter, setLegislaturaFilter] = useState<string>('todos');

  const typeFilter = useMemo<Array<'deputado' | 'senado'>>(() => {
    if (casaSelecionada === 'camara') return ['deputado'];
    if (casaSelecionada === 'senado') return ['senado'];
    return ['deputado', 'senado'];
  }, [casaSelecionada]);

  const { data: rawList, isLoading, isError, error } = useQuery({
    queryKey: ['parliamentarians', partidoFilter, typeFilter.join(',')],
    queryFn: () =>
      listParliamentarians({
        limit: 1000,
        offset: 0,
        party: partidoFilter !== 'todos' ? partidoFilter : undefined,
        type: typeFilter,
      }),
  });

  const allParlamentares = useMemo(() => {
    if (!rawList) return [];
    return rawList.map(mapParliamentarianOutToParlamentar);
  }, [rawList]);

  const parlamentaresDisponiveis = useMemo(() => {
    return allParlamentares.filter((p) => {
      // Filter by search term
      if (searchTerm && !p.nome.toLowerCase().includes(searchTerm.toLowerCase())) {
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

      // Exclude already selected
      if (parlamentaresSelecionados.find((s) => s.id === p.id)) {
        return false;
      }

      return true;
    });
  }, [allParlamentares, searchTerm, partidoFilter, ufFilter, legislaturaFilter, parlamentaresSelecionados]);

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
          <ScrollArea className="h-full pr-4">
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
            <div className="space-y-2">
              {parlamentaresDisponiveis.map((parlamentar) => (
                <div
                  key={parlamentar.id}
                  className="flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-muted/50 transition-colors"
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
                  <Button
                    variant="ghost"
                    size="icon"
                    disabled={favoritosMutating}
                    onClick={() => onAddParlamentar(parlamentar)}
                    className="text-accent hover:text-accent hover:bg-accent/10"
                  >
                    <PlusCircle className="text-[#09e03b]" />
                  </Button>
                </div>
              ))}
              {parlamentaresDisponiveis.length === 0 && (
                <div className="text-center py-8 text-muted-foreground">
                  <p>Nenhum parlamentar encontrado com os filtros selecionados.</p>
                </div>
              )}
            </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Selected Parliamentarians */}
      <Card className="mp-card flex h-[564px] flex-col border-none bg-white">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-[32px] leading-none font-bold text-[#090909]">Parlamentares monitorados</CardTitle>
            <Badge variant="secondary" className="bg-transparent text-[18px] font-medium text-[#7f7c7c]">+{parlamentaresSelecionados.length}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Clique no parlamentar para acessar seu dashboard completo
          </p>
        </CardHeader>
        
        <CardContent className="flex-1 overflow-hidden">
          <ScrollArea className="h-full pr-4">
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
            <div className="space-y-2">
              {parlamentaresSelecionados.map((parlamentar) => (
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
