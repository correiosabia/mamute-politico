/**
 * Classificação do tipo de emenda para exibição.
 *
 * A fonte manda texto livre. Em produção existem exatamente dois valores
 * (medido em 2026-08-12: 24.910 de Finalidade Definida e 4.254 Especiais),
 * mas a checagem é por substring normalizada para sobreviver a variação de
 * caixa, acento e sufixo — mesma política de `is_individual_amendment` no
 * crawler.
 *
 * "Pix" é o termo que a imprensa e os usuários jornalistas usam; o nome
 * oficial fica no tooltip, para a tabela não ficar ilegível.
 */
export type TipoEmendaChave = 'pix' | 'finalidade' | 'desconhecido';

export interface TipoEmenda {
  chave: TipoEmendaChave;
  rotulo: string;
  oficial: string;
}

function normalizar(valor: string): string {
  return valor
    .normalize('NFKD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .split(/\s+/)
    .join(' ')
    .trim();
}

export function classificarTipoEmenda(
  amendmentType: string | null | undefined
): TipoEmenda {
  const oficial = amendmentType ?? '';
  const n = normalizar(oficial);

  // "Finalidade definida" primeiro: o outro casa por "especia(l|is)", que é
  // substring mais curta e poderia capturar variações inesperadas.
  if (n.includes('finalidade definida')) {
    return { chave: 'finalidade', rotulo: 'Finalidade definida', oficial };
  }
  if (n.includes('transferencias especiais') || n.includes('transferencia especial')) {
    return { chave: 'pix', rotulo: 'Pix', oficial };
  }
  return { chave: 'desconhecido', rotulo: '—', oficial };
}
