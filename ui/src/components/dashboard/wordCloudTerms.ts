/**
 * Regras de filtragem da nuvem de palavras.
 *
 * As listas são geridas em Configurações gerais (painel admin) e chegam pela
 * API, por isso as funções recebem as listas como argumento em vez de lerem
 * constantes de módulo.
 *
 * Dois filtros, com efeitos deliberadamente diferentes:
 * - **stopwords** somem palavra a palavra de dentro da expressão;
 * - **termos irrelevantes** descartam a entrada inteira.
 *
 * A distinção importa: "união" é sigla de partido, mas também palavra comum.
 * Como stopword ela mutilaria "união estável"; como termo irrelevante, só
 * descarta a entrada que for exatamente "união".
 */

export interface WordCloudTermsPayload {
  stopwords: string[];
  excluded_terms: string[];
}

export interface WordCloudTermLists {
  stopwords: Set<string>;
  excludedTerms: Set<string>;
}

/** Palavras com até este tamanho nunca viram etiqueta da nuvem. */
const MIN_WORD_LENGTH = 3;

export function normalizeWordCloudTerm(value: string): string {
  return String(value ?? '')
    .normalize('NFC')
    .toLocaleLowerCase('pt-BR')
    .replace(/[^\p{L}\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function buildTermLists(payload: Partial<WordCloudTermsPayload>): WordCloudTermLists {
  const normalizar = (valores?: string[]) =>
    new Set((valores ?? []).map(normalizeWordCloudTerm).filter(Boolean));

  return {
    stopwords: normalizar(payload?.stopwords),
    excludedTerms: normalizar(payload?.excluded_terms),
  };
}

export function filterWordCloudTerm(
  value: string,
  lists: WordCloudTermLists
): string | null {
  const normalized = normalizeWordCloudTerm(value);

  // A entrada inteira é avaliada antes de qualquer remoção: um termo irrelevante
  // composto ("mudança climática") deixaria de casar depois de mexido.
  if (!normalized || lists.excludedTerms.has(normalized)) {
    return null;
  }

  const filtered = normalized
    .split(' ')
    .filter((word) => word.length >= MIN_WORD_LENGTH && !lists.stopwords.has(word))
    .join(' ');

  if (!filtered || lists.excludedTerms.has(filtered)) {
    return null;
  }

  return filtered;
}

/**
 * Rede de segurança para quando a API de configurações não responde. Espelha o
 * seed da migration: nuvem sem filtro nenhum é pior que nuvem desatualizada.
 */
export const FALLBACK_TERM_LISTS: WordCloudTermLists = buildTermLists({
  stopwords: [
    'a', 'ao', 'aos', 'aprovação', 'aprovamos', 'as', 'até', 'com', 'da', 'das',
    'de', 'do', 'dos', 'durante', 'e', 'em', 'na', 'nas', 'no', 'nos', 'o',
    'obrigado', 'os', 'para', 'pec', 'pela', 'pelas', 'pelo', 'pelos', 'por',
    'presidente', 'projeto', 'que', 'relator', 'sem', 'senador', 'senadora',
    'sessão', 'sob', 'sobre', 'um', 'uma', 'gente', 'parlamentar',
  ],
  excluded_terms: [],
});
