import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Header } from './Header';

const flagState: Record<string, boolean> = { busca_candidaturas: false };

vi.mock('@/hooks/useFeatureFlag', () => ({
  useFeatureFlag: (key: string) => flagState[key] === true,
}));

const tokenState = { atual: 'token-de-teste' as string | null };
vi.mock('@/components/auth/ghost-auth/react/useGhostAuth', () => ({
  useGhostAuth: () => tokenState.atual,
  ghostSignOut: vi.fn(),
}));
vi.mock('@/hooks/useIsAdmin', () => ({
  useIsAdmin: () => ({ isAdmin: false, isLoading: false }),
}));
vi.mock('@/components/auth/useLoginModal', () => ({
  useLoginModal: () => ({ openLogin: vi.fn() }),
}));
vi.mock('@/components/auth/useAccountModal', () => ({
  useAccountModal: () => ({ openAccount: vi.fn() }),
}));
vi.mock('@/components/auth/fetchCurrentMember', () => ({ signOut: vi.fn() }));

function renderHeader(props = {}) {
  return render(
    <MemoryRouter>
      <Header {...props} />
    </MemoryRouter>,
  );
}

const buscar = () => screen.queryByRole('link', { name: /BUSCAR/ });

describe('Header — BUSCAR como porta de entrada da tela de candidaturas', () => {
  beforeEach(() => {
    flagState.busca_candidaturas = false;
    tokenState.atual = 'token-de-teste';
  });

  it('não aparece com a flag desligada (o estado de nascimento)', () => {
    renderHeader();
    expect(buscar()).not.toBeInTheDocument();
  });

  it('aparece no header padrão quando a flag está ligada', () => {
    // O ponto da correção: antes o botão só existia no arranjo da própria tela
    // de candidaturas, então ligar a flag não dava acesso a lugar nenhum.
    flagState.busca_candidaturas = true;
    renderHeader();

    expect(buscar()).toHaveAttribute('href', '/candidaturas');
  });

  it('aparece também no arranjo da tela de candidaturas', () => {
    flagState.busca_candidaturas = true;
    renderHeader({ tone: 'blue', actions: 'busca' });

    expect(buscar()).toHaveAttribute('href', '/candidaturas');
    // E o SAIR do design segue lá, que é o que distingue esse arranjo.
    expect(screen.getByRole('button', { name: 'Sair' })).toHaveTextContent('SAIR');
  });

  it('não aparece para visitante deslogado, mesmo com a flag ligada', () => {
    // A rota exige sessão: oferecer a porta levaria a um redirect.
    flagState.busca_candidaturas = true;
    tokenState.atual = null;
    renderHeader();

    expect(buscar()).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Iniciar Sessão' })).toBeInTheDocument();
  });
});
