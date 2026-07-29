import { describe, expect, it } from 'vitest';

import {
  FALLBACK_TERM_LISTS,
  buildTermLists,
  filterWordCloudTerm,
  normalizeWordCloudTerm,
} from './wordCloudTerms';

/**
 * Dois filtros com efeitos deliberadamente diferentes:
 * - stopword: some palavra a palavra de dentro da expressão;
 * - termo irrelevante: descarta a entrada inteira.
 */

const listas = buildTermLists({
  stopwords: ['de', 'do', 'o', 'projeto', 'sessão', 'presidente'],
  excluded_terms: ['mudança climática', 'bloco'],
});

describe('normalizeWordCloudTerm', () => {
  it('normaliza caixa, pontuação e espaços', () => {
    expect(normalizeWordCloudTerm('  Reforma,   TRIBUTÁRIA!  ')).toBe('reforma tributária');
  });

  it('preserva acentuação', () => {
    expect(normalizeWordCloudTerm('SAÚDE')).toBe('saúde');
  });
});

describe('filterWordCloudTerm', () => {
  it('remove uma stopword isolada', () => {
    expect(filterWordCloudTerm('Presidente', listas)).toBeNull();
  });

  it('remove stopwords de dentro de uma expressão', () => {
    expect(filterWordCloudTerm('O projeto de lei', listas)).toBe('lei');
  });

  it('descarta expressão formada só por stopwords', () => {
    expect(filterWordCloudTerm('de do o', listas)).toBeNull();
  });

  it('descarta palavra configurada como irrelevante', () => {
    expect(filterWordCloudTerm('Bloco', listas)).toBeNull();
  });

  it('descarta expressão configurada como irrelevante', () => {
    expect(filterWordCloudTerm('Mudança Climática', listas)).toBeNull();
  });

  it('descarta a expressão irrelevante antes de remover stopwords', () => {
    // Sem a checagem prévia, "mudança climática" viraria outra coisa e escaparia.
    expect(filterWordCloudTerm('  mudança   climática  ', listas)).toBeNull();
  });

  it('mantém palavras significativas da expressão', () => {
    expect(filterWordCloudTerm('Sessão extraordinária', listas)).toBe('extraordinária');
  });

  it('descarta palavras de até 2 letras', () => {
    expect(filterWordCloudTerm('ao ir', listas)).toBeNull();
  });

  it('retorna null quando não sobra conteúdo', () => {
    expect(filterWordCloudTerm('   ', listas)).toBeNull();
    expect(filterWordCloudTerm('!!!', listas)).toBeNull();
  });

  it('deixa passar termo que não bate em nenhuma lista', () => {
    expect(filterWordCloudTerm('Amazônia', listas)).toBe('amazônia');
  });

  it('descarta o resultado se o que sobrou virou termo irrelevante', () => {
    // "o bloco" -> remove a stopword "o" -> sobra "bloco", que é irrelevante.
    expect(filterWordCloudTerm('o bloco', listas)).toBeNull();
  });
});

describe('buildTermLists', () => {
  it('normaliza as listas vindas da API', () => {
    const l = buildTermLists({ stopwords: ['  PRESIDENTE '], excluded_terms: ['  BLOCO '] });

    expect(filterWordCloudTerm('presidente', l)).toBeNull();
    expect(filterWordCloudTerm('bloco', l)).toBeNull();
  });

  it('listas vazias não derrubam a nuvem', () => {
    const l = buildTermLists({ stopwords: [], excluded_terms: [] });

    // Sem listas nada é filtrado por configuração, mas a regra de tamanho
    // mínimo continua valendo — ela não depende do que o admin cadastrou.
    expect(filterWordCloudTerm('O projeto de lei', l)).toBe('projeto lei');
    expect(filterWordCloudTerm('Amazônia', l)).toBe('amazônia');
  });

  it('tolera resposta incompleta da API', () => {
    const l = buildTermLists({} as never);

    expect(filterWordCloudTerm('Amazônia', l)).toBe('amazônia');
  });
});

describe('FALLBACK_TERM_LISTS', () => {
  it('filtra o básico quando a API não responde', () => {
    // Nuvem sem filtro nenhum é pior que nuvem com filtro desatualizado.
    expect(filterWordCloudTerm('presidente', FALLBACK_TERM_LISTS)).toBeNull();
    expect(filterWordCloudTerm('O projeto de lei', FALLBACK_TERM_LISTS)).toBe('lei');
  });
});
