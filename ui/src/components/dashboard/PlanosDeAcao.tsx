import { useQuery } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';

import { listActionPlans } from '@/api/endpoints';
import { textoPrestacao } from '@/lib/prestacaoContas';

const BRL = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
});

function formatBRL(value?: string | null): string {
  if (value == null || value === '') return '—';
  const parsed = Number(value);
  return Number.isFinite(parsed) ? BRL.format(parsed) : '—';
}

interface PlanosDeAcaoProps {
  amendmentCode: string;
}

/**
 * Entes que receberam a emenda Pix e o estado da prestação de contas de cada um.
 *
 * A query vive aqui dentro: quem não expandiu a linha não dispara request —
 * são ~58 mil planos na base e a listagem traz até 200 emendas.
 */
export function PlanosDeAcao({ amendmentCode }: PlanosDeAcaoProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['action-plans', amendmentCode],
    queryFn: () => listActionPlans(amendmentCode),
  });

  const anoCorrente = new Date().getFullYear();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-3 text-[13px] text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        Carregando beneficiários…
      </div>
    );
  }

  if (isError) {
    return (
      <p className="py-3 text-[13px] text-muted-foreground">
        Não foi possível carregar os beneficiários desta emenda.
      </p>
    );
  }

  if (!data || data.length === 0) {
    return (
      <p className="py-3 text-[13px] text-muted-foreground">
        Nenhum plano de ação registrado no Transferegov para esta emenda.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-black/[0.06]">
      {data.map((plano) => {
        const semPrestacao = plano.prestacao_situacao == null;
        return (
          <li
            key={plano.id_plano_acao}
            className="flex flex-col gap-1 py-2 sm:flex-row sm:items-baseline sm:justify-between"
          >
            <div className="min-w-0">
              <span className="text-[13px] font-semibold text-foreground">
                {plano.beneficiario_nome ?? '—'}
              </span>
              {plano.beneficiario_uf && (
                <span className="ml-2 text-[12px] text-muted-foreground">
                  {plano.beneficiario_uf}
                </span>
              )}
            </div>
            <div className="flex shrink-0 items-baseline gap-3">
              <span
                className={
                  semPrestacao
                    ? 'text-[12px] text-muted-foreground'
                    : 'text-[12px] font-semibold text-foreground'
                }
              >
                {textoPrestacao(plano, anoCorrente)}
              </span>
              {plano.prestacao_valor_executado != null && (
                <span className="whitespace-nowrap text-[12px] text-muted-foreground">
                  {formatBRL(plano.prestacao_valor_executado)} executado
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
