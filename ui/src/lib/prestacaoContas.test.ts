import { describe, expect, it } from 'vitest';
import { prestou, textoPrestacao } from './prestacaoContas';

const base = {
  prestacao_tipo: null,
  prestacao_valor_executado: null,
};

describe('textoPrestacao', () => {
  it('ano corrente sem prestacao diz que o prazo esta aberto', () => {
    expect(
      textoPrestacao({ ...base, ano: 2026, prestacao_situacao: null }, 2026)
    ).toMatch(/prazo aberto/i);
  });

  it('ano fechado sem prestacao NUNCA acusa', () => {
    const texto = textoPrestacao(
      { ...base, ano: 2023, prestacao_situacao: null },
      2026
    );
    expect(texto).toMatch(/sem prestação registrada/i);
    expect(texto).not.toMatch(/não prestou|sonegou|irregular|omiss/i);
  });

  it('plano sem ano cai no caso conservador, nao no acusatorio', () => {
    expect(
      textoPrestacao({ ...base, ano: null, prestacao_situacao: null }, 2026)
    ).toMatch(/sem prestação registrada/i);
  });

  it('mostra o tipo quando ha prestacao disponibilizada', () => {
    expect(
      textoPrestacao(
        {
          ano: 2024,
          prestacao_situacao: 'DISPONIBILIZADO',
          prestacao_tipo: 'Final',
          prestacao_valor_executado: '100.00',
        },
        2026
      )
    ).toMatch(/final/i);
  });

  it('distingue em elaboracao de disponibilizada', () => {
    expect(
      textoPrestacao(
        { ...base, ano: 2024, prestacao_situacao: 'EM_ELABORACAO' },
        2026
      )
    ).toMatch(/em elaboração/i);
  });
});

describe('prestou', () => {
  it('conta qualquer relatorio registrado', () => {
    expect(prestou({ prestacao_situacao: 'EM_ELABORACAO' })).toBe(true);
    expect(prestou({ prestacao_situacao: null })).toBe(false);
  });
});
