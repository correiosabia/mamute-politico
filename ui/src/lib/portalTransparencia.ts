const PORTAL_EMENDA_DETALHE =
  'https://portaldatransparencia.gov.br/emendas/detalhe';

/**
 * Monta o link para a página oficial de uma emenda no Portal da Transparência.
 *
 * A página do Portal já traz os empenhos e as fases de execução da emenda, o
 * que dispensa coletar os documentos por conta própria só para dar
 * rastreabilidade ao usuário.
 *
 * `codigoEmenda` sozinho identifica a emenda — os demais parâmetros que o
 * Portal acrescenta ao navegar (`codigoTipoEmenda`, `ordenarPor`, `direcao`)
 * são de ordenação e não fazem parte da identidade do recurso.
 */
export function getPortalEmendaUrl(
  amendmentCode: string | null | undefined
): string | null {
  if (amendmentCode == null) return null;

  const code = amendmentCode.trim();
  // O codigo e sempre numerico (ano + autor + numero). Recusar o resto evita
  // montar URL a partir de valor inesperado da fonte.
  if (!/^\d+$/.test(code)) return null;

  return `${PORTAL_EMENDA_DETALHE}?codigoEmenda=${encodeURIComponent(code)}`;
}
