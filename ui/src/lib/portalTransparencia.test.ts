import { describe, expect, it } from 'vitest';
import { getPortalEmendaUrl } from './portalTransparencia';

describe('getPortalEmendaUrl', () => {
  it('monta o link de detalhe a partir do codigo da emenda', () => {
    expect(getPortalEmendaUrl('202638970001')).toBe(
      'https://portaldatransparencia.gov.br/emendas/detalhe?codigoEmenda=202638970001'
    );
  });

  it('ignora espaco em volta', () => {
    expect(getPortalEmendaUrl('  202637990004  ')).toContain(
      'codigoEmenda=202637990004'
    );
  });

  it('devolve null para ausente ou vazio', () => {
    expect(getPortalEmendaUrl(null)).toBeNull();
    expect(getPortalEmendaUrl(undefined)).toBeNull();
    expect(getPortalEmendaUrl('')).toBeNull();
    expect(getPortalEmendaUrl('   ')).toBeNull();
  });

  it('recusa codigo nao numerico', () => {
    // Defesa contra valor inesperado da fonte virando URL.
    expect(getPortalEmendaUrl('abc')).toBeNull();
    expect(getPortalEmendaUrl('2026;drop')).toBeNull();
    expect(getPortalEmendaUrl('../../etc')).toBeNull();
  });

  it('produz URL https valida', () => {
    const url = new URL(getPortalEmendaUrl('202632980010') as string);
    expect(url.protocol).toBe('https:');
    expect(url.hostname).toBe('portaldatransparencia.gov.br');
    expect(url.searchParams.get('codigoEmenda')).toBe('202632980010');
  });
});
