import { useQuery } from '@tanstack/react-query';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  getElectoralHistory,
  type ElectoralHistoryEntryOut,
} from '@/api/endpoints';
import { getSafeExternalUrl } from '@/lib/safeExternalUrl';
import { ExternalLink, Loader2 } from 'lucide-react';

interface TrajetoriaTabProps {
  parliamentarianId: number;
}

const BRL = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
});

/** Valores chegam como string para não perder centavo; só viram número aqui. */
function formatBRL(value?: string | null): string {
  if (value == null || value === '') return '—';
  const parsed = Number(value);
  return Number.isFinite(parsed) ? BRL.format(parsed) : '—';
}

function resultBadgeClass(result?: string | null): string {
  const value = (result ?? '').toLowerCase();
  if (value.startsWith('eleito') || value === '2º turno')
    return 'bg-green-100 text-green-800';
  if (value === 'concorrendo') return 'bg-amber-100 text-amber-800';
  if (value === 'suplente') return 'bg-gray-100 text-gray-700';
  return 'bg-red-50 text-red-700';
}

export function TrajetoriaTab({ parliamentarianId }: TrajetoriaTabProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['electoral-history', parliamentarianId],
    queryFn: () => getElectoralHistory(parliamentarianId),
  });

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (isError) {
    return (
      <p className="p-4 text-sm text-muted-foreground">
        Não foi possível carregar a trajetória eleitoral.
      </p>
    );
  }

  const entries = data?.entries ?? [];
  // Gráfico em ordem cronológica; a lista fica na ordem da API (ano desc).
  const chartData = [...entries]
    .reverse()
    .filter((entry) => entry.declared_assets != null)
    .map((entry) => ({
      year: entry.year,
      patrimonio: Number(entry.declared_assets),
    }));

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto">
      <span className="inline-flex w-fit items-center rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
        Prévia — visível só para administradores
      </span>

      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Histórico eleitoral ainda não coletado para este parlamentar.
        </p>
      ) : (
        <>
          {chartData.length >= 2 && (
            <div className="h-56 w-full shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={chartData}
                  margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="rgba(0,0,0,0.06)"
                  />
                  <XAxis dataKey="year" tick={{ fontSize: 12 }} />
                  <YAxis
                    tick={{ fontSize: 12 }}
                    width={90}
                    tickFormatter={(value: number) =>
                      BRL.format(value).replace(/,00$/, '')
                    }
                  />
                  <Tooltip
                    formatter={(value: number) => [
                      BRL.format(value),
                      'Patrimônio declarado',
                    ]}
                    labelFormatter={(year) => `Eleição de ${year}`}
                  />
                  <Line
                    type="monotone"
                    dataKey="patrimonio"
                    stroke="#b45309"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Ano</TableHead>
                <TableHead>Cargo</TableHead>
                <TableHead>Local</TableHead>
                <TableHead>Partido</TableHead>
                <TableHead>Resultado</TableHead>
                <TableHead className="text-right">
                  Patrimônio declarado
                </TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry: ElectoralHistoryEntryOut) => {
                const safeUrl = entry.source_link
                  ? getSafeExternalUrl(entry.source_link)
                  : null;
                return (
                  <TableRow key={`${entry.year}-${entry.office}-${entry.state}`}>
                    <TableCell className="font-medium">{entry.year}</TableCell>
                    <TableCell>{entry.office ?? '—'}</TableCell>
                    <TableCell>
                      {entry.locality ?? entry.state ?? '—'}
                    </TableCell>
                    <TableCell>{entry.party ?? '—'}</TableCell>
                    <TableCell>
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${resultBadgeClass(entry.result)}`}
                      >
                        {entry.result ?? '—'}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      {formatBRL(entry.declared_assets)}
                    </TableCell>
                    <TableCell>
                      {safeUrl && (
                        <a
                          href={safeUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                        >
                          ver no TSE <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </>
      )}
    </div>
  );
}
