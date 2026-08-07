import { useQuery } from '@tanstack/react-query';
import { listAmendments } from '@/api/endpoints';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Loader2 } from 'lucide-react';

interface EmendasTableProps {
  parliamentarianId: number;
  year?: number;
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

function textOrDash(value?: string | null): string {
  return value == null || value === '' ? '—' : value;
}

export function EmendasTable({ parliamentarianId, year }: EmendasTableProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['amendments', parliamentarianId, year],
    queryFn: () =>
      listAmendments({
        parliamentarian_id: parliamentarianId,
        year,
        limit: 200,
        sort_by: 'committed_value',
        sort_order: 'desc',
      }),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-10 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span>Carregando emendas...</span>
      </div>
    );
  }

  if (isError) {
    return (
      <p className="py-10 text-center text-muted-foreground">
        Falha ao carregar as emendas do parlamentar.
      </p>
    );
  }

  if (!data || data.length === 0) {
    return (
      <p className="py-10 text-center text-muted-foreground">
        Nenhuma emenda encontrada para este parlamentar.
      </p>
    );
  }

  return (
    <div className="max-h-[440px] overflow-y-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nº</TableHead>
            <TableHead>Localidade do gasto</TableHead>
            <TableHead>Função</TableHead>
            <TableHead className="text-right">Empenhado</TableHead>
            <TableHead className="text-right">Pago</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((emenda) => (
            <TableRow key={emenda.id}>
              <TableCell className="whitespace-nowrap">
                {textOrDash(emenda.amendment_number)}
              </TableCell>
              <TableCell>{textOrDash(emenda.spending_locality)}</TableCell>
              <TableCell>{textOrDash(emenda.function)}</TableCell>
              <TableCell className="whitespace-nowrap text-right">
                {formatBRL(emenda.committed_value)}
              </TableCell>
              <TableCell className="whitespace-nowrap text-right">
                {formatBRL(emenda.paid_value)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
