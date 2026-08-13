import type { TipoEmendaChave } from './tipoEmenda';

const CONSULTA_PLANO_ACAO =
  'https://especiais.transferegov.sistema.gov.br/transferencia-especial/plano-acao/consulta';
const PORTAL_GERAL = 'https://portal.transferegov.sistema.gov.br/portal/home';

/**
 * Consulta pública do Transferegov correspondente ao tipo da emenda.
 *
 * A consulta é um formulário de busca: **não aceita o código da emenda por
 * query string**. Por isso a tela nunca promete "a prestação desta emenda"
 * atrás do link. Para as Pix os dados vêm da nossa base, e o link serve só
 * para o usuário conferir na fonte; para as de Finalidade Definida, que ainda
 * não têm API, é tudo que existe.
 */
export function getTransferegovConsultaUrl(
  chave: TipoEmendaChave
): string | null {
  if (chave === 'pix') return CONSULTA_PLANO_ACAO;
  if (chave === 'finalidade') return PORTAL_GERAL;
  return null;
}
