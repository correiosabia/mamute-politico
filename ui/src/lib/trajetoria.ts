/**
 * Derivações puras da trajetória eleitoral (CS-60, parte visual).
 *
 * Tudo aqui é FATO derivado do TSE, nunca inferência sobre conduta:
 * - faixa de mandato = eleição vencida + duração constitucional do cargo;
 * - variação = diferença entre patrimônios declarados em eleições
 *   consecutivas COM declaração (a drenagem de bens é incremental e deixa
 *   buracos que precisam ser pulados, não zerados).
 *
 * Valores nominais: correção inflacionária ficou fora de escopo por decisão
 * de produto (CS-54). Quem exibe deve dizer isso.
 */

import type { ElectoralHistoryEntryOut } from '@/api/endpoints';

/**
 * "Eleito", "Eleito por QP", "Eleito por média"… O TSE devolve texto cru.
 * "Não eleito" não começa com "eleito", então não passa. "Suplente" e
 * "2º turno" ficam de fora de propósito: suplente pode nunca assumir e
 * 2º turno é classificação, não vitória — a base não sabe o desfecho.
 */
export function isElectedResult(result?: string | null): boolean {
  return (result ?? '').trim().toLowerCase().startsWith('eleito');
}

/** Duração constitucional do mandato pelo cargo (Senador 8; demais 4). */
export function mandateYears(office?: string | null): number {
  return (office ?? '').toLowerCase().includes('senador') ? 8 : 4;
}

export interface MandateBand {
  startYear: number;
  endYear: number;
  office: string;
}

/**
 * Faixas de mandato para sombrear o gráfico, recortadas ao domínio do eixo.
 * Convenção: a faixa vai do ano da eleição vencida até eleição+duração —
 * no eixo de anos ELEITORAIS, é o intervalo governado por aquela vitória.
 * Faixa que ficar com largura zero após o recorte é descartada.
 */
export function mandateBands(
  entries: ElectoralHistoryEntryOut[],
  domainMin: number,
  domainMax: number
): MandateBand[] {
  const bands: MandateBand[] = [];
  const chronological = [...entries].sort((a, b) => a.year - b.year);
  for (const entry of chronological) {
    if (!isElectedResult(entry.result)) continue;
    const startYear = Math.max(entry.year, domainMin);
    const endYear = Math.min(entry.year + mandateYears(entry.office), domainMax);
    if (endYear <= startYear) continue;
    bands.push({ startYear, endYear, office: entry.office ?? 'Mandato' });
  }
  return bands;
}

export interface AssetVariation {
  fromYear: number;
  toYear: number;
  absolute: number;
  /** null quando a base é zero — não existe percentual de divisão por zero. */
  percent: number | null;
}

function declaredAsNumber(entry: ElectoralHistoryEntryOut): number | null {
  if (entry.declared_assets == null || entry.declared_assets === '') return null;
  const parsed = Number(entry.declared_assets);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Variações entre eleições consecutivas com patrimônio declarado, em ordem
 * cronológica. Eleição sem declaração (assets ainda não drenados) é pulada:
 * a variação liga as duas declarações mais próximas, nunca inventa zero.
 */
export function assetVariations(
  entries: ElectoralHistoryEntryOut[]
): AssetVariation[] {
  const declared = [...entries]
    .sort((a, b) => a.year - b.year)
    .map((entry) => ({ year: entry.year, value: declaredAsNumber(entry) }))
    .filter((point): point is { year: number; value: number } =>
      point.value != null
    );

  const variations: AssetVariation[] = [];
  for (let i = 1; i < declared.length; i++) {
    const from = declared[i - 1];
    const to = declared[i];
    variations.push({
      fromYear: from.year,
      toYear: to.year,
      absolute: to.value - from.value,
      percent: from.value === 0 ? null : ((to.value - from.value) / from.value) * 100,
    });
  }
  return variations;
}

/** A variação que TERMINA no ano dado (para a linha da tabela daquele ano). */
export function variationForYear(
  variations: AssetVariation[],
  year: number
): AssetVariation | undefined {
  return variations.find((variation) => variation.toYear === year);
}
