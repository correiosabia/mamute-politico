import { useQuery } from '@tanstack/react-query';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
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
import {
  assetVariations,
  mandateBands,
  variationForYear,
  type AssetVariation,
} from '@/lib/trajetoria';
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

const PCT = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });

/**
 * "+R$ 320.000,00 (+45%)" / "−R$ 150.000,00 (−9%)". Absoluto E percentual
 * juntos, sempre: percentual sozinho explode com base pequena e vira a
 * manchete errada que a CS-60 existe para evitar. Sem percentual quando a
 * base é zero.
 */
function formatVariation(variation: AssetVariation): string {
  const sinal = variation.absolute >= 0 ? '+' : '−';
  const valor = BRL.format(Math.abs(variation.absolute));
  if (variation.percent == null) return `${sinal}${valor}`;
  return `${sinal}${valor} (${sinal}${PCT.format(Math.abs(variation.percent))}%)`;
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

  const years = chartData.map((point) => point.year);
  // Faixas de mandato (fato: eleição vencida + duração do cargo) sombreiam o
  // fundo do gráfico; variações alimentam tooltip e a coluna da tabela.
  const bands =
    years.length >= 2
      ? mandateBands(entries, Math.min(...years), Math.max(...years))
      : [];
  const variations = assetVariations(entries);

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto">
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
                  <XAxis
                    dataKey="year"
                    type="number"
                    domain={['dataMin', 'dataMax']}
                    ticks={years}
                    allowDecimals={false}
                    tick={{ fontSize: 12 }}
                  />
                  <YAxis
                    tick={{ fontSize: 12 }}
                    width={90}
                    tickFormatter={(value: number) =>
                      BRL.format(value).replace(/,00$/, '')
                    }
                  />
                  {bands.map((band) => (
                    <ReferenceArea
                      key={`${band.startYear}-${band.office}`}
                      x1={band.startYear}
                      x2={band.endYear}
                      fill="#1f2b44"
                      fillOpacity={0.06}
                      label={{
                        value: band.office,
                        position: 'insideTopLeft',
                        fontSize: 10,
                        fill: '#64748b',
                      }}
                    />
                  ))}
                  <Tooltip
                    formatter={(value: number) => [
                      BRL.format(value),
                      'Patrimônio declarado',
                    ]}
                    labelFormatter={(year) => {
                      const variation = variationForYear(
                        variations,
                        Number(year)
                      );
                      return variation
                        ? `Eleição de ${year} · desde ${variation.fromYear}: ${formatVariation(variation)}`
                        : `Eleição de ${year}`;
                    }}
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
              <p className="mt-1 text-xs text-muted-foreground">
                Faixas sombreadas indicam mandato eletivo (eleição vencida +
                duração do cargo). Valores nominais declarados ao TSE, sem
                correção inflacionária.
              </p>
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
                <TableHead className="text-right">Variação</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry: ElectoralHistoryEntryOut) => {
                const safeUrl = entry.source_link
                  ? getSafeExternalUrl(entry.source_link)
                  : null;
                const variation = variationForYear(variations, entry.year);
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
                    <TableCell
                      className="whitespace-nowrap text-right text-muted-foreground"
                      title={
                        variation
                          ? `Em relação à eleição de ${variation.fromYear} (valores nominais)`
                          : undefined
                      }
                    >
                      {variation ? formatVariation(variation) : '—'}
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
