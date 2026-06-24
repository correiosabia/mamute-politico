import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { Parlamentar } from '@/types/parlamentar';
import { ParlamentarInfo } from './ParlamentarInfo';

const baseParlamentar: Parlamentar = {
  id: '42',
  nome: 'Ada Lovelace',
  nomeCompleto: 'Ada Byron Lovelace',
  foto: '',
  partido: { sigla: 'IND', nome: 'Independente' },
  uf: 'SP',
  casa: 'camara',
  legislatura: 57,
  situacao: 'Exercício',
};

describe('ParlamentarInfo', () => {
  it('renders safe parliamentarian links', () => {
    render(
      <ParlamentarInfo
        parlamentar={{
          ...baseParlamentar,
          site: 'https://example.com/site',
          biografiaLink: 'https://www.camara.leg.br/deputados/42/biografia',
          redesSociais: [{ name: 'Rede oficial', profileUrl: 'https://social.example/ada' }],
        }}
      />
    );

    expect(screen.getByRole('link', { name: 'Ver site oficial' })).toHaveAttribute(
      'href',
      'https://example.com/site'
    );
    expect(screen.getByRole('link', { name: 'Ver biografia oficial' })).toHaveAttribute(
      'href',
      'https://www.camara.leg.br/deputados/42/biografia'
    );
    expect(screen.getByRole('link', { name: 'Rede oficial' })).toHaveAttribute(
      'href',
      'https://social.example/ada'
    );
  });

  it('does not render unsafe parliamentarian link schemes', () => {
    render(
      <ParlamentarInfo
        parlamentar={{
          ...baseParlamentar,
          site: 'javascript:alert(1)',
          biografiaLink: 'data:text/html,<script>alert(1)</script>',
          redesSociais: [
            { name: 'Rede insegura', profileUrl: 'javascript:alert(2)' },
            { name: 'Rede segura', profileUrl: 'https://social.example/safe' },
          ],
        }}
      />
    );

    expect(screen.queryByRole('link', { name: 'Ver site oficial' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Ver biografia oficial' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Rede insegura' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Rede segura' })).toHaveAttribute(
      'href',
      'https://social.example/safe'
    );
  });
});
