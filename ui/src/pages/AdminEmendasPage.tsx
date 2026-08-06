import { useQuery } from '@tanstack/react-query';
import { AdminShell } from '@/components/layout/AdminShell';
import { listUnmatchedAmendmentAuthors } from '@/api/admin';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Loader2 } from 'lucide-react';

const BRL = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
});

function formatBRL(value: string): string {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? BRL.format(parsed) : '—';
}

const STATUS_LABEL: Record<string, string> = {
  unmatched: 'Sem correspondência',
  ambiguous: 'Homônimo',
};

export default function AdminEmendasPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['admin', 'amendments', 'unmatched'],
    queryFn: () => listUnmatchedAmendmentAuthors(),
  });

  const hasRows = data != null && data.length > 0;

  return (
    <AdminShell footer="mammoth">
      <div>
        <h1 className="text-[36px] font-bold leading-none text-[#393939] md:text-[48px]">
          Emendas não casadas
        </h1>
        <p className="mt-1 text-[18px] font-normal text-[#383838]">
          O Portal da Transparência publica o autor da emenda apenas como texto.
          Estes nomes não corresponderam a nenhum parlamentar da base — em geral
          são de quem já deixou o mandato.
        </p>
      </div>

      <div className="mp-card bg-white p-6">
        {isLoading && (
          <div className="flex items-center justify-center gap-2 py-10 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>Carregando...</span>
          </div>
        )}

        {isError && (
          <p className="py-10 text-center text-muted-foreground">
            Falha ao carregar a auditoria de emendas.
          </p>
        )}

        {!isLoading && !isError && !hasRows && (
          <p className="py-10 text-center text-muted-foreground">
            Todas as emendas casaram com algum parlamentar.
          </p>
        )}

        {hasRows && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Autor (como veio da fonte)</TableHead>
                <TableHead>Motivo</TableHead>
                <TableHead className="text-right">Emendas</TableHead>
                <TableHead className="text-right">Valor empenhado</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((linha) => (
                <TableRow key={`${linha.author_name_raw}-${linha.match_status}`}>
                  <TableCell>{linha.author_name_raw ?? '—'}</TableCell>
                  <TableCell>
                    {STATUS_LABEL[linha.match_status] ?? linha.match_status}
                  </TableCell>
                  <TableCell className="text-right">{linha.amendment_count}</TableCell>
                  <TableCell className="whitespace-nowrap text-right">
                    {formatBRL(linha.committed_total)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </AdminShell>
  );
}
