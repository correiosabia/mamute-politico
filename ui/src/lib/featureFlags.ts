/**
 * Registro das feature flags da interface.
 *
 * Esta lista é a fonte da verdade de QUAIS flags existem; o banco guarda só em
 * que estado cada uma está. Chave sem linha no banco vale `off`, então feature
 * nova nasce desligada sem exigir migration.
 *
 * REGRAS
 *
 * 1. Uma flag, um portão, no ponto de montagem. O custo de uma flag não é a
 *    flag: é em quantos lugares ela é lida. Se a feature é uma tela ou uma
 *    aba, o portão fica onde ela é montada. Se for um enriquecimento dentro
 *    de um componente existente, o portão fica dentro desse componente e não
 *    vaza para o pai.
 *
 * 2. Flag não aninha em flag. Para melhorar algo que ainda está atrás de uma
 *    flag, estenda a feature existente — não crie uma segunda flag dentro
 *    dela. Como a feature ainda não saiu para ninguém, não há o que separar.
 *
 * 3. Isto é controle de apresentação, não fronteira de segurança. A API
 *    continua aberta e qualquer um a chama direto. Nunca use este mecanismo
 *    para esconder algo que não pode ser visto.
 *
 * COMO REMOVER UMA FLAG (quando a feature está consolidada em produção)
 *
 * 1. Apague a linha daqui.
 * 2. Rode `tsc`. Ele quebra em todos os call sites, porque
 *    `useFeatureFlag('x')` deixa de tipar.
 * 3. Desembrulhe cada condicional que o compilador apontou.
 * 4. `tsc` verde = terminou. Está provado que não sobrou uso.
 *
 * O passo 2 é o que substitui disciplina por garantia: a remoção falha em voz
 * alta, não silenciosamente.
 *
 * A linha no banco fica órfã e inerte, e some do /admin/configuracoes
 * sozinha, porque a tela renderiza a partir deste registro. Não existe (nem
 * deve existir) um segundo mecanismo para esconder o controle.
 */
export const FEATURE_FLAGS = {
  trajetoria: {
    label: 'Aba Trajetória no dashboard do parlamentar',
    since: '2026-08-10',
  },
  emendas_prestacao: {
    label: 'Prestação de contas das emendas Pix',
    since: '2026-08-12',
  },
  marcacoes_pessoais: {
    label: 'Ordem pessoal e tags nos parlamentares monitorados',
    since: '2026-08-12',
  },
} as const;

export type FeatureFlagKey = keyof typeof FEATURE_FLAGS;

/** Dias desde o nascimento da flag, para a tela cobrar flag esquecida. */
export function flagAgeInDays(since: string, hoje = new Date()): number {
  const nascimento = new Date(`${since}T00:00:00Z`);
  const ms = hoje.getTime() - nascimento.getTime();
  return Math.max(0, Math.floor(ms / 86_400_000));
}

/** Acima disto a tela destaca a flag como candidata a remoção do código. */
export const FLAG_AGE_WARNING_DAYS = 60;
