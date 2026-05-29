import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listRollCallVotes, type RollCallVoteSortBy, type SortOrder } from '@/api/endpoints';
import { mapRollCallVoteOutToVotacao } from '@/api/mappers';
import {
  buildFilterChips,
  formatDateTimeLabel,
  toIsoOrUndefined,
  useDraftAppliedFilters,
} from '@/components/dashboard/filterUtils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  ArrowUpDown,
  Ban,
  Filter,
  Loader2,
  Minus,
  ThumbsDown,
  ThumbsUp,
  UserX,
  X,
} from 'lucide-react';

interface VotacoesTableProps {
  limit?: number;
  parliamentarianId?: number;
}

interface DateRangeFilters {
  created_from: string;
  created_to: string;
  updated_from: string;
  updated_to: string;
}

const EMPTY_FILTERS: DateRangeFilters = {
  created_from: '',
  created_to: '',
  updated_from: '',
  updated_to: '',
};

const SORT_BY_LABELS: Record<RollCallVoteSortBy, string> = {
  created_at: 'Data de criação',
  updated_at: 'Data de atualização',
  id: 'ID',
  parliamentarian_id: 'Parlamentar',
  proposition_id: 'Proposição',
};

const VISIBLE_SORT_KEYS: RollCallVoteSortBy[] = ['created_at', 'updated_at', 'id'];

export function VotacoesTable({ limit = 10, parliamentarianId }: VotacoesTableProps) {
  const {
    draftFilters,
    setDraftFilters,
    appliedFilters,
    filtersOpen,
    onFiltersOpenChange,
    applyFilters,
    clearAllFilters,
    clearFilter,
  } = useDraftAppliedFilters(EMPTY_FILTERS);
  const [sortBy, setSortBy] = useState<RollCallVoteSortBy>('created_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  const apiParams = useMemo(
    () => ({
      limit,
      offset: 0,
      parliamentarian_id: parliamentarianId,
      created_from: toIsoOrUndefined(appliedFilters.created_from),
      created_to: toIsoOrUndefined(appliedFilters.created_to),
      updated_from: toIsoOrUndefined(appliedFilters.updated_from),
      updated_to: toIsoOrUndefined(appliedFilters.updated_to),
      sort_by: sortBy,
      sort_order: sortOrder,
    }),
    [limit, parliamentarianId, appliedFilters, sortBy, sortOrder]
  );

  const { data: rawList, isLoading, isError } = useQuery({
    queryKey: ['roll-call-votes', apiParams],
    queryFn: () => listRollCallVotes(apiParams),
  });

  const votacoes = rawList != null ? rawList.map(mapRollCallVoteOutToVotacao) : [];

  const activeFilterChips = buildFilterChips(
    appliedFilters,
    [
      ['created_from', 'Criado a partir de'],
      ['created_to', 'Criado até'],
      ['updated_from', 'Atualizado a partir de'],
      ['updated_to', 'Atualizado até'],
    ] as const
  );

  const getVotoIcon = (voto: string) => {
    switch (voto) {
      case 'Sim':
        return <ThumbsUp className="h-4 w-4 text-success" />;
      case 'Não':
        return <ThumbsDown className="h-4 w-4 text-destructive" />;
      case 'Abstenção':
        return <Minus className="h-4 w-4 text-warning" />;
      case 'Obstrução':
        return <Ban className="h-4 w-4 text-muted-foreground" />;
      case 'Ausente':
        return <UserX className="h-4 w-4 text-muted-foreground" />;
      default:
        return null;
    }
  };

  const getVotoBadge = (voto: string) => {
    switch (voto) {
      case 'Sim':
        return 'success';
      case 'Não':
        return 'destructive';
      case 'Abstenção':
        return 'warning';
      default:
        return 'secondary';
    }
  };

  return (
    <div className="flex h-full w-full flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Popover
          open={filtersOpen}
          onOpenChange={onFiltersOpenChange}
        >
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className="gap-2">
              <Filter className="h-3.5 w-3.5" />
              Filtrar
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-80 bg-popover" align="start">
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Criado a partir de</label>
                <input
                  type="datetime-local"
                  value={draftFilters.created_from}
                  onChange={(e) =>
                    setDraftFilters((prev) => ({ ...prev, created_from: e.target.value }))
                  }
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Criado até</label>
                <input
                  type="datetime-local"
                  value={draftFilters.created_to}
                  onChange={(e) =>
                    setDraftFilters((prev) => ({ ...prev, created_to: e.target.value }))
                  }
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Atualizado a partir de</label>
                <input
                  type="datetime-local"
                  value={draftFilters.updated_from}
                  onChange={(e) =>
                    setDraftFilters((prev) => ({ ...prev, updated_from: e.target.value }))
                  }
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Atualizado até</label>
                <input
                  type="datetime-local"
                  value={draftFilters.updated_to}
                  onChange={(e) =>
                    setDraftFilters((prev) => ({ ...prev, updated_to: e.target.value }))
                  }
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>
              <div className="flex items-center justify-between gap-2 pt-2">
                <Button variant="ghost" size="sm" onClick={clearAllFilters}>
                  Limpar filtros
                </Button>
                <Button size="sm" onClick={applyFilters}>
                  Aplicar
                </Button>
              </div>
            </div>
          </PopoverContent>
        </Popover>

        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className="gap-2">
              <ArrowUpDown className="h-3.5 w-3.5" />
              Ordenar
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-72 bg-popover" align="start">
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Campo</label>
                <Select value={sortBy} onValueChange={(v) => setSortBy(v as RollCallVoteSortBy)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-popover">
                    {VISIBLE_SORT_KEYS.map((key) => (
                      <SelectItem key={key} value={key}>
                        {SORT_BY_LABELS[key]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Direção</label>
                <Select value={sortOrder} onValueChange={(v) => setSortOrder(v as SortOrder)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-popover">
                    <SelectItem value="desc">Decrescente</SelectItem>
                    <SelectItem value="asc">Crescente</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </PopoverContent>
        </Popover>

        {activeFilterChips.map((chip) => (
          <Badge key={chip.key} variant="secondary" className="gap-1">
            <span className="text-[11px]">
              {chip.label}: {formatDateTimeLabel(chip.value)}
            </span>
            <X
              className="h-3 w-3 cursor-pointer"
              onClick={() => clearFilter(chip.key as keyof DateRangeFilters)}
            />
          </Badge>
        ))}
      </div>

      <div className="min-h-0 flex-1 w-full overflow-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>Carregando votações...</span>
          </div>
        ) : isError ? (
          <div className="text-center py-8 text-muted-foreground text-sm">
            Falha ao carregar votações.
          </div>
        ) : (
          <>
            <Table className="min-w-[720px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Votação</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead>Voto</TableHead>
                  <TableHead>Descrição</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {votacoes.map((votacao) => (
                  <TableRow
                    key={votacao.id}
                    role={votacao.proposicaoLink ? 'link' : undefined}
                    tabIndex={votacao.proposicaoLink ? 0 : -1}
                    onClick={() => {
                      if (!votacao.proposicaoLink) return;
                      window.open(votacao.proposicaoLink, '_blank', 'noopener,noreferrer');
                    }}
                    onKeyDown={(e) => {
                      if (!votacao.proposicaoLink) return;
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        window.open(votacao.proposicaoLink, '_blank', 'noopener,noreferrer');
                      }
                    }}
                    className={[
                      'hover:bg-muted/50',
                      votacao.proposicaoLink
                        ? 'cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
                        : 'cursor-default',
                    ].join(' ')}
                  >
                    <TableCell className="font-medium text-sm max-w-[200px] truncate" title={votacao.proposicao}>
                      {votacao.proposicao}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {votacao.data ? new Date(votacao.data).toLocaleDateString('pt-BR') : '—'}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2 whitespace-nowrap">
                        {getVotoIcon(votacao.voto)}
                        <Badge
                          variant={getVotoBadge(votacao.voto) as 'success' | 'destructive' | 'warning' | 'secondary'}
                          className="whitespace-nowrap text-[10px]"
                        >
                          {votacao.voto}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-muted-foreground">{votacao.descricao || '—'}</span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {votacoes.length === 0 && (
              <div className="text-center py-8 text-muted-foreground text-sm">
                Nenhuma votação encontrada.
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
