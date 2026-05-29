import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  listPropositions,
  listPropositionsByParliamentarian,
  type PropositionSortBy,
  type SortOrder,
} from '@/api/endpoints';
import { mapPropositionOutToProposicao } from '@/api/mappers';
import {
  buildFilterChips,
  formatDateOnlyLabel,
  formatDateTimeLabel,
  toIsoOrUndefined,
  useDraftAppliedFilters,
} from '@/components/dashboard/filterUtils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
import { getProposicaoSituacaoBadgeVariant } from '@/lib/proposicaoSituacao';
import { ArrowUpDown, Filter, Loader2, X } from 'lucide-react';

interface ProposicoesTableProps {
  limit?: number;
  parliamentarianId?: string;
}

interface PropositionsFilters {
  year: string;
  acronym: string;
  presentation_date_from: string;
  presentation_date_to: string;
  created_from: string;
  created_to: string;
  updated_from: string;
  updated_to: string;
}

const EMPTY_FILTERS: PropositionsFilters = {
  year: '',
  acronym: '',
  presentation_date_from: '',
  presentation_date_to: '',
  created_from: '',
  created_to: '',
  updated_from: '',
  updated_to: '',
};

const SORT_BY_LABELS: Record<PropositionSortBy, string> = {
  created_at: 'Data de criação',
  updated_at: 'Data de atualização',
  title: 'Título',
  presentation_date: 'Data de apresentação',
  presentation_year: 'Ano de apresentação',
  proposition_number: 'Número da proposição',
};

const SORT_KEYS: PropositionSortBy[] = [
  'created_at',
  'updated_at',
  'title',
  'presentation_date',
  'presentation_year',
  'proposition_number',
];

export function ProposicoesTable({ limit = 10, parliamentarianId }: ProposicoesTableProps) {
  const numericId = parliamentarianId != null && parliamentarianId !== '' ? Number(parliamentarianId) : NaN;
  const isParliamentarianScope = Number.isInteger(numericId) && numericId > 0;

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
  const [sortBy, setSortBy] = useState<PropositionSortBy>('created_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  const apiParams = useMemo(() => {
    const yearNum = appliedFilters.year ? Number(appliedFilters.year) : undefined;
    return {
      year: yearNum != null && Number.isFinite(yearNum) ? yearNum : undefined,
      acronym: appliedFilters.acronym || undefined,
      presentation_date_from: appliedFilters.presentation_date_from || undefined,
      presentation_date_to: appliedFilters.presentation_date_to || undefined,
      created_from: toIsoOrUndefined(appliedFilters.created_from),
      created_to: toIsoOrUndefined(appliedFilters.created_to),
      updated_from: toIsoOrUndefined(appliedFilters.updated_from),
      updated_to: toIsoOrUndefined(appliedFilters.updated_to),
      sort_by: sortBy,
      sort_order: sortOrder,
    };
  }, [appliedFilters, sortBy, sortOrder]);

  const { data: rawList, isLoading, isError } = useQuery({
    queryKey: [
      'propositions',
      isParliamentarianScope ? 'by-parliamentarian' : 'list',
      numericId,
      limit,
      apiParams,
    ],
    queryFn: () =>
      isParliamentarianScope
        ? listPropositionsByParliamentarian(numericId, { limit, ...apiParams })
        : listPropositions({ limit, offset: 0, ...apiParams }),
  });

  const proposicoes = rawList != null ? rawList.map(mapPropositionOutToProposicao) : [];

  const activeFilterChips = buildFilterChips(
    appliedFilters,
    [
      ['year', 'Ano'],
      ['acronym', 'Sigla'],
      ['presentation_date_from', 'Apresentado a partir de'],
      ['presentation_date_to', 'Apresentado até'],
      ['created_from', 'Criado a partir de'],
      ['created_to', 'Criado até'],
      ['updated_from', 'Atualizado a partir de'],
      ['updated_to', 'Atualizado até'],
    ] as const
  );

  const renderChipValue = (key: keyof PropositionsFilters, value: string) => {
    if (key === 'year' || key === 'acronym') return value;
    if (key === 'presentation_date_from' || key === 'presentation_date_to') {
      return formatDateOnlyLabel(value);
    }
    return formatDateTimeLabel(value);
  };

  return (
    <div className="space-y-4">
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
          <PopoverContent className="w-96 bg-popover" align="start">
            <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Ano</label>
                  <Input
                    type="number"
                    inputMode="numeric"
                    placeholder="2025"
                    value={draftFilters.year}
                    onChange={(e) =>
                      setDraftFilters((prev) => ({ ...prev, year: e.target.value }))
                    }
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Sigla</label>
                  <Input
                    type="text"
                    placeholder="PL, PEC..."
                    value={draftFilters.acronym}
                    onChange={(e) =>
                      setDraftFilters((prev) => ({ ...prev, acronym: e.target.value }))
                    }
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Apresentado entre</label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="date"
                    value={draftFilters.presentation_date_from}
                    onChange={(e) =>
                      setDraftFilters((prev) => ({
                        ...prev,
                        presentation_date_from: e.target.value,
                      }))
                    }
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                  <input
                    type="date"
                    value={draftFilters.presentation_date_to}
                    onChange={(e) =>
                      setDraftFilters((prev) => ({
                        ...prev,
                        presentation_date_to: e.target.value,
                      }))
                    }
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Criado entre</label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="datetime-local"
                    value={draftFilters.created_from}
                    onChange={(e) =>
                      setDraftFilters((prev) => ({ ...prev, created_from: e.target.value }))
                    }
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                  <input
                    type="datetime-local"
                    value={draftFilters.created_to}
                    onChange={(e) =>
                      setDraftFilters((prev) => ({ ...prev, created_to: e.target.value }))
                    }
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Atualizado entre</label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="datetime-local"
                    value={draftFilters.updated_from}
                    onChange={(e) =>
                      setDraftFilters((prev) => ({ ...prev, updated_from: e.target.value }))
                    }
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                  <input
                    type="datetime-local"
                    value={draftFilters.updated_to}
                    onChange={(e) =>
                      setDraftFilters((prev) => ({ ...prev, updated_to: e.target.value }))
                    }
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                </div>
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
                <Select value={sortBy} onValueChange={(v) => setSortBy(v as PropositionSortBy)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-popover">
                    {SORT_KEYS.map((key) => (
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
              {chip.label}: {renderChipValue(chip.key, chip.value)}
            </span>
            <X
              className="h-3 w-3 cursor-pointer"
              onClick={() => clearFilter(chip.key as keyof PropositionsFilters)}
            />
          </Badge>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span>Carregando proposições...</span>
        </div>
      ) : isError ? (
        <div className="text-center py-8 text-muted-foreground text-sm">
          Falha ao carregar proposições.
        </div>
      ) : (
        <div className="max-h-[400px] w-full overflow-auto">
          <Table className="min-w-[760px]">
            <TableHeader>
              <TableRow>
                <TableHead>Tipo/Número</TableHead>
                <TableHead>Ementa</TableHead>
                <TableHead>Tema</TableHead>
                <TableHead>Data</TableHead>
                <TableHead>Situação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {proposicoes.map((proposicao) => (
                <TableRow
                  key={proposicao.id}
                  role={proposicao.link ? 'link' : undefined}
                  tabIndex={proposicao.link ? 0 : -1}
                  onClick={() => {
                    if (!proposicao.link) return;
                    window.open(proposicao.link, '_blank', 'noopener,noreferrer');
                  }}
                  onKeyDown={(e) => {
                    if (!proposicao.link) return;
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      window.open(proposicao.link, '_blank', 'noopener,noreferrer');
                    }
                  }}
                  className={[
                    'hover:bg-muted/50',
                    proposicao.link ? 'cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2' : 'cursor-default',
                  ].join(' ')}
                >
                  <TableCell className="font-medium">
                    {proposicao.tipo} {proposicao.numero}/{proposicao.ano}
                  </TableCell>
                  <TableCell className="max-w-[300px] truncate text-sm text-muted-foreground">
                    {proposicao.ementa}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="whitespace-nowrap text-[10px]">
                      {proposicao.tema}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {proposicao.dataApresentacao
                      ? new Date(proposicao.dataApresentacao).toLocaleDateString('pt-BR')
                      : '—'}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={getProposicaoSituacaoBadgeVariant(proposicao.situacao)}
                      className="whitespace-nowrap text-[10px]"
                    >
                      {proposicao.situacao}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {proposicoes.length === 0 && (
            <div className="text-center py-8 text-muted-foreground text-sm">
              Nenhuma proposição encontrada.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
