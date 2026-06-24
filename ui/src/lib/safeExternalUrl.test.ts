import { describe, expect, it, vi } from 'vitest';

import { getSafeExternalUrl, openSafeExternalUrl } from '@/lib/safeExternalUrl';

describe('getSafeExternalUrl', () => {
  it('allows absolute http and https links', () => {
    expect(getSafeExternalUrl('https://www.camara.leg.br/proposicoesWeb/abc')).toBe(
      'https://www.camara.leg.br/proposicoesWeb/abc'
    );
    expect(getSafeExternalUrl('http://www25.senado.leg.br/web/atividade')).toBe(
      'http://www25.senado.leg.br/web/atividade'
    );
  });

  it('rejects script, data, relative, and invalid links', () => {
    expect(getSafeExternalUrl('javascript:alert(1)')).toBeNull();
    expect(getSafeExternalUrl('data:text/html,<script>alert(1)</script>')).toBeNull();
    expect(getSafeExternalUrl('/relative/path')).toBeNull();
    expect(getSafeExternalUrl('not a url')).toBeNull();
  });
});

describe('openSafeExternalUrl', () => {
  it('does not call window.open for unsafe links', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    expect(openSafeExternalUrl('javascript:alert(1)')).toBe(false);

    expect(openSpy).not.toHaveBeenCalled();
  });

  it('opens safe links with noopener and noreferrer', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    expect(openSafeExternalUrl('https://www25.senado.leg.br/web/atividade')).toBe(true);

    expect(openSpy).toHaveBeenCalledWith(
      'https://www25.senado.leg.br/web/atividade',
      '_blank',
      'noopener,noreferrer'
    );
  });
});
