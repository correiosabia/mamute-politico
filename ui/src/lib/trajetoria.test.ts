import { describe, expect, it } from 'vitest';
import {
  assetVariations,
  isElectedResult,
  mandateBands,
  mandateYears,
  variationForYear,
} from './trajetoria';
import type { ElectoralHistoryEntryOut } from '@/api/endpoints';

function entry(over: Partial<ElectoralHistoryEntryOut>): ElectoralHistoryEntryOut {
  return { year: 2022, assets_count: 0, ...over } as ElectoralHistoryEntryOut;
}

describe('isElectedResult', () => {
  it('reconhece as variantes de eleito do TSE', () => {
    expect(isElectedResult('Eleito')).toBe(true);
    expect(isElectedResult('Eleito por QP')).toBe(true);
    expect(isElectedResult('ELEITO POR MÉDIA')).toBe(true);
  });

  it('nunca trata como mandato o que não é', () => {
    expect(isElectedResult('Não eleito')).toBe(false);
    // Suplente pode nunca assumir; 2º turno é só classificação — a base não
    // sabe o desfecho, então não afirmamos mandato.
    expect(isElectedResult('Suplente')).toBe(false);
    expect(isElectedResult('2º turno')).toBe(false);
    expect(isElectedResult('Concorrendo')).toBe(false);
    expect(isElectedResult(null)).toBe(false);
    expect(isElectedResult(undefined)).toBe(false);
  });
});

describe('mandateYears', () => {
  it('senador tem mandato de 8 anos; o resto, 4', () => {
    expect(mandateYears('Senador')).toBe(8);
    expect(mandateYears('SENADOR')).toBe(8);
    expect(mandateYears('Deputado Federal')).toBe(4);
    expect(mandateYears('Governador')).toBe(4);
    expect(mandateYears('Prefeito')).toBe(4);
    expect(mandateYears(null)).toBe(4);
  });
});

describe('mandateBands', () => {
  const HISTORICO = [
    entry({ year: 2014, office: 'Deputado Estadual', result: 'Eleito' }),
    entry({ year: 2018, office: 'Deputado Federal', result: 'Eleito por QP' }),
    entry({ year: 2022, office: 'Senador', result: 'Não eleito' }),
    entry({ year: 2026, office: 'Governador', result: 'Concorrendo' }),
  ];

  it('cria uma faixa por eleição vencida, com a duração do cargo', () => {
    const bands = mandateBands(HISTORICO, 2014, 2026);
    expect(bands).toEqual([
      { startYear: 2014, endYear: 2018, office: 'Deputado Estadual' },
      { startYear: 2018, endYear: 2022, office: 'Deputado Federal' },
    ]);
  });

  it('recorta a faixa ao domínio do gráfico e descarta largura zero', () => {
    // Senador eleito na última eleição do gráfico: mandato vai além do
    // domínio; sem recorte a faixa some ou estoura o eixo.
    const historico = [
      entry({ year: 2018, office: 'Senador', result: 'Eleito' }),
      entry({ year: 2022, office: 'Presidente', result: 'Não eleito' }),
    ];
    expect(mandateBands(historico, 2018, 2022)).toEqual([
      { startYear: 2018, endYear: 2022, office: 'Senador' },
    ]);
    // faixa que ficaria com largura zero é descartada
    expect(mandateBands([historico[0]], 2018, 2018)).toEqual([]);
  });
});

describe('assetVariations', () => {
  it('calcula variação absoluta e percentual entre eleições consecutivas', () => {
    const historico = [
      entry({ year: 2026, declared_assets: '3200000.00' }),
      entry({ year: 2022, declared_assets: '1000000.00' }),
      entry({ year: 2018, declared_assets: '800000.00' }),
    ];
    const variations = assetVariations(historico);
    expect(variations).toHaveLength(2);
    expect(variations[0]).toMatchObject({
      fromYear: 2018,
      toYear: 2022,
      absolute: 200000,
    });
    expect(variations[0].percent).toBeCloseTo(25);
    expect(variations[1]).toMatchObject({ fromYear: 2022, toYear: 2026 });
    expect(variations[1].percent).toBeCloseTo(220);
  });

  it('pula eleições sem patrimônio declarado (drenagem incremental)', () => {
    const historico = [
      entry({ year: 2026, declared_assets: '300.00' }),
      entry({ year: 2022, declared_assets: null }),
      entry({ year: 2018, declared_assets: '100.00' }),
    ];
    const variations = assetVariations(historico);
    expect(variations).toHaveLength(1);
    expect(variations[0]).toMatchObject({ fromYear: 2018, toYear: 2026 });
    expect(variations[0].percent).toBeCloseTo(200);
  });

  it('base zero não divide: percent fica null', () => {
    const historico = [
      entry({ year: 2022, declared_assets: '50000.00' }),
      entry({ year: 2018, declared_assets: '0.00' }),
    ];
    const [v] = assetVariations(historico);
    expect(v.absolute).toBe(50000);
    expect(v.percent).toBeNull();
  });
});

describe('variationForYear', () => {
  it('acha a variação que TERMINA no ano pedido', () => {
    const variations = assetVariations([
      entry({ year: 2022, declared_assets: '200.00' }),
      entry({ year: 2018, declared_assets: '100.00' }),
    ]);
    expect(variationForYear(variations, 2022)?.fromYear).toBe(2018);
    expect(variationForYear(variations, 2018)).toBeUndefined();
  });
});
