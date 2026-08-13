import { describe, expect, it } from 'vitest';
import { classificarTipoEmenda } from './tipoEmenda';

describe('classificarTipoEmenda', () => {
  it('reconhece transferencia especial como Pix', () => {
    const r = classificarTipoEmenda(
      'Emenda Individual - Transferências Especiais'
    );
    expect(r.chave).toBe('pix');
    expect(r.rotulo).toBe('Pix');
  });

  it('reconhece finalidade definida', () => {
    const r = classificarTipoEmenda(
      'Emenda Individual - Transferências com Finalidade Definida'
    );
    expect(r.chave).toBe('finalidade');
    expect(r.rotulo).toBe('Finalidade definida');
  });

  it('sobrevive a acento, caixa e espaco diferentes', () => {
    expect(
      classificarTipoEmenda('EMENDA INDIVIDUAL  -  TRANSFERENCIAS ESPECIAIS')
        .chave
    ).toBe('pix');
  });

  it('tipo desconhecido ou nulo nao inventa rotulo', () => {
    expect(classificarTipoEmenda(null).chave).toBe('desconhecido');
    expect(classificarTipoEmenda(undefined).chave).toBe('desconhecido');
    expect(classificarTipoEmenda('Emenda de Bancada').chave).toBe(
      'desconhecido'
    );
  });

  it('guarda o nome oficial para o tooltip', () => {
    const r = classificarTipoEmenda(
      'Emenda Individual - Transferências Especiais'
    );
    expect(r.oficial).toBe('Emenda Individual - Transferências Especiais');
  });
});
