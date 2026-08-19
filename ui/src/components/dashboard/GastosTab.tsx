import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { getExpensesSummary, listExpenses } from '@/api/endpoints';
import type { ExpenseSummaryOut } from '@/api/types';
import { getSafeExternalUrl, openSafeExternalUrl } from '@/lib/safeExternalUrl';
import { ExternalLink, Loader2 } from 'lucide-react';

interface GastosTabProps {
  parliamentarianId: number;
}

/** Cobertura da coleta definida na CS-57; anos anteriores não estão no banco. */
const FIRST_YEAR = 2022;

/** Acima disto os tipos menores colapsam em "Outras" para a legenda caber. */
const MAX_CHART_TYPES = 6;

const MESES = [
  'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
  'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez',
];

/** Paleta fixa: a ordem segue o ranking de gasto do ano, não o tipo. */
const CORES = [
  '#1b76ff', '#f59e0b', '#10b981', '#8b5cf6', '#ef4444', '#0ea5e9', '#6b7280',
];

const OUTRAS = 'Outras despesas';

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

function textOrDash(value?: string | null): string {
  return value == null || value === '' ? '—' : value;
}

/** Tipos da fonte são frases longas (Senado); a legenda usa só o começo. */
function shortType(tipo: string): string {
  const clean = tipo.replace(/\.$/, '');
  if (clean.length <= 32) return clean;
  const cut = clean.slice(0, 32);
  return `${cut.slice(0, cut.lastIndexOf(' '))}…`;
}

interface ChartRow {
  mes: string;
  [serie: string]: string | number;
}

/**
 * Pivota o `monthly` da API (mês × tipo × total) nas linhas do gráfico
 * empilhado: uma linha por mês, uma chave por série. Os tipos além dos
 * MAX_CHART_TYPES maiores do ano colapsam em "Outras despesas".
 */
export function pivotMonthly(summary: ExpenseSummaryOut): {
  rows: ChartRow[];
  series: string[];
} {
  const totalPorTipo = new Map<string, number>();
  for (const cell of summary.monthly) {
    totalPorTipo.set(
      cell.expense_type,
      (totalPorTipo.get(cell.expense_type) ?? 0) + Number(cell.total)
    );
  }
  const principais = [...totalPorTipo.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, MAX_CHART_TYPES)
    .map(([tipo]) => tipo);

  const series = principais.map(shortType);
  const temOutras = totalPorTipo.size > principais.length;
  if (temOutras) series.push(OUTRAS);

  const rotulo = new Map(principais.map((tipo) => [tipo, shortType(tipo)]));

  const rows: ChartRow[] = MESES.map((mes) => ({ mes }));
  for (const cell of summary.monthly) {
    const row = rows[cell.month - 1];
    if (!row) continue;
    const serie = rotulo.get(cell.expense_type) ?? OUTRAS;
    row[serie] = ((row[serie] as number) ?? 0) + Number(cell.total);
  }
  return { rows, series };
}

export function GastosTab({ parliamentarianId }: GastosTabProps) {
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const anos: number[] = [];
  for (let y = currentYear; y >= FIRST_YEAR; y--) anos.push(y);

  const summaryQuery = useQuery({
    queryKey: ['expenses-summary', parliamentarianId, year],
    queryFn: () => getExpensesSummary(parliamentarianId, year),
  });
  const listQuery = useQuery({
    queryKey: ['expenses', parliamentarianId, year],
    queryFn: () =>
      listExpenses({
        parliamentarian_id: parliamentarianId,
        year,
        limit: 200,
        sort_by: 'net_value',
        sort_order: 'desc',
      }),
  });

  if (summaryQuery.isLoading || listQuery.isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-10 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span>Carregando gastos...</span>
      </div>
    );
  }

  if (summaryQuery.isError || listQuery.isError) {
    return (
      <p className="py-10 text-center text-muted-foreground">
        Falha ao carregar os gastos do parlamentar.
      </p>
    );
  }

  const summary = summaryQuery.data;
  const gastos = listQuery.data ?? [];

  const seletorDeAno = (
    <div className="flex items-center justify-between gap-3">
      <p className="text-sm text-muted-foreground">
        Cota parlamentar: total de {formatBRL(summary?.total)} em {year}
      </p>
      <Select value={String(year)} onValueChange={(v) => setYear(Number(v))}>
        <SelectTrigger className="w-[110px]" aria-label="Ano dos gastos">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {anos.map((ano) => (
            <SelectItem key={ano} value={String(ano)}>
              {ano}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );

  if (!summary || summary.count === 0) {
    return (
      <div className="space-y-4">
        {seletorDeAno}
        <p className="py-10 text-center text-muted-foreground">
          Nenhum gasto de cota encontrado para este parlamentar em {year}.
        </p>
      </div>
    );
  }

  const { rows, series } = pivotMonthly(summary);

  return (
    <div className="max-h-[440px] space-y-6 overflow-y-auto pr-1">
      {seletorDeAno}

      <div className="h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="mes" tick={{ fontSize: 11 }} />
            <YAxis
              tick={{ fontSize: 11 }}
              tickFormatter={(v: number) =>
                v >= 1000 ? `${Math.round(v / 1000)} mil` : String(v)
              }
            />
            <Tooltip formatter={(value: number) => BRL.format(value)} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {series.map((serie, i) => (
              <Bar
                key={serie}
                dataKey={serie}
                stackId="gastos"
                fill={CORES[i % CORES.length]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-foreground">
          Principais fornecedores
        </h3>
        <ul className="space-y-1">
          {summary.top_suppliers.slice(0, 5).map((f) => (
            <li
              key={`${f.supplier_name}-${f.supplier_id}`}
              className="flex items-baseline justify-between gap-4 text-sm"
            >
              <span className="min-w-0 truncate" title={f.supplier_id ?? undefined}>
                {textOrDash(f.supplier_name)}
              </span>
              <span className="whitespace-nowrap text-muted-foreground">
                {formatBRL(f.total)} · {f.count}{' '}
                {f.count === 1 ? 'despesa' : 'despesas'}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Mês</TableHead>
            <TableHead>Tipo de despesa</TableHead>
            <TableHead>Fornecedor</TableHead>
            <TableHead className="text-right">Valor</TableHead>
            <TableHead className="w-[44px] text-right" aria-label="Documento fiscal" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {gastos.map((gasto) => {
            const safeLink = getSafeExternalUrl(gasto.document_url ?? null);
            return (
              <TableRow key={gasto.id} className="hover:bg-muted/50">
                <TableCell className="whitespace-nowrap">
                  {MESES[gasto.month - 1] ?? gasto.month}
                </TableCell>
                <TableCell title={gasto.expense_type}>
                  {shortType(gasto.expense_type)}
                </TableCell>
                <TableCell title={gasto.supplier_id ?? undefined}>
                  {textOrDash(gasto.supplier_name)}
                </TableCell>
                <TableCell className="whitespace-nowrap text-right">
                  {formatBRL(gasto.net_value)}
                </TableCell>
                <TableCell className="text-right">
                  {safeLink && (
                    <button
                      type="button"
                      aria-label="Ver o documento fiscal na fonte"
                      title={
                        gasto.house === 'camara'
                          ? 'Ver a nota fiscal (PDF da Câmara)'
                          : 'Ver a despesa no Portal de Transparência do Senado'
                      }
                      onClick={() => openSafeExternalUrl(safeLink)}
                      className="ml-auto flex h-6 w-6 items-center justify-center rounded focus:outline-none focus:ring-2 focus:ring-ring"
                    >
                      <ExternalLink
                        className="h-4 w-4 text-muted-foreground"
                        aria-hidden="true"
                      />
                    </button>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
