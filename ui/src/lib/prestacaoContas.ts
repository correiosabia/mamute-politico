import type { ActionPlanOut } from '@/api/types';

/**
 * Como descrever a prestação de contas de um plano de ação.
 *
 * REGRA EDITORIAL: a tela nunca diz "não prestou contas". A cobertura medida
 * na fonte cai de 58% (planos de 2022) para 6% (planos de 2026) — o buraco do
 * ano corrente é prazo em aberto, não omissão. Tratar os dois casos igual
 * transformaria dado faltante em acusação.
 */
export function textoPrestacao(
  plano: Pick<
    ActionPlanOut,
    'ano' | 'prestacao_situacao' | 'prestacao_tipo' | 'prestacao_valor_executado'
  >,
  anoCorrente: number
): string {
  if (plano.prestacao_situacao == null) {
    return plano.ano != null && plano.ano >= anoCorrente
      ? 'sem prestação — prazo aberto'
      : 'sem prestação registrada';
  }

  if (plano.prestacao_situacao === 'EM_ELABORACAO') {
    return 'prestação em elaboração';
  }
  if (plano.prestacao_situacao === 'ENVIADO_PARA_ANALISE') {
    return 'prestação enviada para análise';
  }
  return plano.prestacao_tipo
    ? `prestação ${plano.prestacao_tipo.toLowerCase()}`
    : 'prestação disponibilizada';
}

/** Um plano conta como "prestou" quando a fonte registrou qualquer relatório. */
export function prestou(plano: Pick<ActionPlanOut, 'prestacao_situacao'>): boolean {
  return plano.prestacao_situacao != null;
}
