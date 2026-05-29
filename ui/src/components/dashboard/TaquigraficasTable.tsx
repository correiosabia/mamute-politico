import { useMemo, useState } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import {
  getSpeechAnalysis,
  listSpeechesTranscripts,
  type SortOrder,
  type SpeechesTranscriptSortBy,
} from '@/api/endpoints';
import {
  buildFilterChips,
  formatDateOnlyLabel,
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
import { ArrowUpDown, Filter, Loader2, X } from 'lucide-react';

interface TaquigraficasTableProps {
  limit?: number;
  parliamentarianId?: number;
}

interface SpeechFilters {
  date_from: string;
  date_to: string;
  created_from: string;
  created_to: string;
  updated_from: string;
  updated_to: string;
}

const EMPTY_FILTERS: SpeechFilters = {
  date_from: '',
  date_to: '',
  created_from: '',
  created_to: '',
  updated_from: '',
  updated_to: '',
};

const SORT_BY_LABELS: Record<SpeechesTranscriptSortBy, string> = {
  date: 'Data do discurso',
  created_at: 'Data de criação',
  updated_at: 'Data de atualização',
  id: 'ID',
  parliamentarian_id: 'Parlamentar',
};

const VISIBLE_SORT_KEYS: SpeechesTranscriptSortBy[] = [
  'date',
  'created_at',
  'updated_at',
  'id',
];

export function TaquigraficasTable({ limit = 20, parliamentarianId }: TaquigraficasTableProps) {
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
  const [sortBy, setSortBy] = useState<SpeechesTranscriptSortBy>('date');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  const apiParams = useMemo(
    () => ({
      limit,
      offset: 0,
      parliamentarian_id: parliamentarianId,
      date_from: appliedFilters.date_from || undefined,
      date_to: appliedFilters.date_to || undefined,
      created_from: toIsoOrUndefined(appliedFilters.created_from),
      created_to: toIsoOrUndefined(appliedFilters.created_to),
      updated_from: toIsoOrUndefined(appliedFilters.updated_from),
      updated_to: toIsoOrUndefined(appliedFilters.updated_to),
      sort_by: sortBy,
      sort_order: sortOrder,
    }),
    [limit, parliamentarianId, appliedFilters, sortBy, sortOrder]
  );

  const { data: speeches, isLoading, isError } = useQuery({
    queryKey: ['speeches-transcripts', apiParams],
    queryFn: () => listSpeechesTranscripts(apiParams),
  });

  const analysisQueries = useQueries({
    queries: (speeches ?? []).map((speech) => ({
      queryKey: ['speech-analysis', speech.id],
      queryFn: () => getSpeechAnalysis(speech.id),
    })),
  });

  const analysisBySpeechId = new Map(
    (speeches ?? []).map((speech, index) => [speech.id, analysisQueries[index]?.data])
  );

  const activeFilterChips = buildFilterChips(
    appliedFilters,
    [
      ['date_from', 'Data a partir de'],
      ['date_to', 'Data até'],
      ['created_from', 'Criado a partir de'],
      ['created_to', 'Criado até'],
      ['updated_from', 'Atualizado a partir de'],
      ['updated_to', 'Atualizado até'],
    ] as const
  );

  const renderChipValue = (key: keyof SpeechFilters, value: string) => {
    if (key === 'date_from' || key === 'date_to') {
      return formatDateOnlyLabel(value);
    }
    return formatDateTimeLabel(value);
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
          <PopoverContent className="w-96 bg-popover" align="start">
            <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
              <div className="space-y-2">
                <label className="text-sm font-medium">Discurso entre</label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="date"
                    value={draftFilters.date_from}
                    onChange={(e) =>
                      setDraftFilters((prev) => ({ ...prev, date_from: e.target.value }))
                    }
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                  <input
                    type="date"
                    value={draftFilters.date_to}
                    onChange={(e) =>
                      setDraftFilters((prev) => ({ ...prev, date_to: e.target.value }))
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
                <Select
                  value={sortBy}
                  onValueChange={(v) => setSortBy(v as SpeechesTranscriptSortBy)}
                >
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
              {chip.label}: {renderChipValue(chip.key, chip.value)}
            </span>
            <X
              className="h-3 w-3 cursor-pointer"
              onClick={() => clearFilter(chip.key as keyof SpeechFilters)}
            />
          </Badge>
        ))}
      </div>

      <div className="min-h-0 flex-1 w-full overflow-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>Carregando notas taquigráficas...</span>
          </div>
        ) : isError ? (
          <div className="text-center py-8 text-muted-foreground text-sm">
            Falha ao carregar notas taquigráficas.
          </div>
        ) : (
          <>
            <Table className="min-w-[760px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  <TableHead>Sessão</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Resumo</TableHead>
                  <TableHead>Análise</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(speeches ?? []).map((speech) => (
                  <TableRow
                    key={speech.id}
                    role={speech.speech_link ? 'link' : undefined}
                    tabIndex={speech.speech_link ? 0 : -1}
                    onClick={() => {
                      if (!speech.speech_link) return;
                      window.open(speech.speech_link, '_blank', 'noopener,noreferrer');
                    }}
                    onKeyDown={(e) => {
                      if (!speech.speech_link) return;
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        window.open(speech.speech_link, '_blank', 'noopener,noreferrer');
                      }
                    }}
                    className={[
                      'hover:bg-muted/50',
                      speech.speech_link
                        ? 'cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
                        : 'cursor-default',
                    ].join(' ')}
                  >
                    <TableCell className="text-sm text-muted-foreground">
                      {speech.date ? new Date(speech.date).toLocaleDateString('pt-BR') : '—'}
                    </TableCell>
                    <TableCell className="text-sm">{speech.session_number ?? '—'}</TableCell>
                    <TableCell className="text-sm">{speech.type ?? '—'}</TableCell>
                    <TableCell className="text-sm text-muted-foreground max-w-[360px] truncate">
                      {speech.summary ?? speech.speech_text ?? '—'}
                    </TableCell>
                    <TableCell>
                      {analysisQueries.some((q) => q.isLoading) ? (
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          <span>Carregando...</span>
                        </div>
                      ) : analysisBySpeechId.get(speech.id) ? (
                        <div className="flex items-center gap-1 whitespace-nowrap">
                          {(analysisBySpeechId.get(speech.id)?.keywords[0]?.term ??
                            analysisBySpeechId.get(speech.id)?.keywords[0]?.keyword) && (
                            <Badge variant="info" className="whitespace-nowrap text-[10px]">
                              {(analysisBySpeechId.get(speech.id)?.keywords[0]?.term ??
                                analysisBySpeechId.get(speech.id)?.keywords[0]?.keyword) as string}
                            </Badge>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">Sem análise</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {(speeches ?? []).length === 0 && (
              <div className="text-center py-8 text-muted-foreground text-sm">
                Nenhuma nota taquigráfica encontrada.
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
