import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { PaywallOverlay } from './PaywallOverlay';

describe('PaywallOverlay', () => {
  it('borra o conteudo e mostra o CTA de assinatura', () => {
    render(
      <PaywallOverlay recurso="a aba Emendas">
        <p>conteudo real</p>
      </PaywallOverlay>
    );
    // O conteudo (previa truncada do backend) continua montado, sob o blur.
    expect(screen.getByText('conteudo real')).toBeInTheDocument();
    expect(
      screen.getByText(/exclusivo para assinantes/i)
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /assinar/i })
    ).toHaveAttribute(
      'href',
      expect.stringContaining('/#/portal/account/plans')
    );
  });

  it('nomeia o recurso no texto do CTA', () => {
    render(
      <PaywallOverlay recurso="a aba Trajetória">
        <div />
      </PaywallOverlay>
    );
    expect(screen.getByText(/a aba Trajetória/)).toBeInTheDocument();
  });
});
