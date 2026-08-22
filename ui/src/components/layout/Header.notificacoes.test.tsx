import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Header } from './Header';

// `busca_candidaturas` ligada de propósito: é o que deixa o BUSCAR em tela e
// permite afirmar que a flag do sino não interfere nos outros botões.
const flagState: Record<string, boolean> = {
  notificacoes: false,
  busca_candidaturas: true,
};

vi.mock('@/hooks/useFeatureFlag', () => ({
  useFeatureFlag: (key: string) => flagState[key] === true,
}));

// Logado: o bloco BUSCAR + sino + SAIR só existe com sessão.
vi.mock('@/components/auth/ghost-auth/react/useGhostAuth', () => ({
  useGhostAuth: () => 'token-de-teste',
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
      <Header tone="blue" actions="busca" {...props} />
    </MemoryRouter>,
  );
}

describe('Header — sino de notificações atrás da flag', () => {
  beforeEach(() => {
    flagState.notificacoes = false;
    flagState.busca_candidaturas = true;
  });

  it('não mostra o sino com a flag desligada (o estado de nascimento)', () => {
    renderHeader();

    expect(screen.queryByRole('button', { name: 'Notificações' })).not.toBeInTheDocument();
    // O resto das ações do design continua: a flag é só do sino.
    expect(screen.getByRole('link', { name: /BUSCAR/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sair' })).toBeInTheDocument();
  });

  it('mostra o sino com a flag ligada, e sem badge quando não há contagem', () => {
    flagState.notificacoes = true;
    renderHeader();

    const sino = screen.getByRole('button', { name: 'Notificações' });
    expect(sino).toBeInTheDocument();
    // Sem fonte de dados, nenhum número é inventado.
    expect(sino).toHaveTextContent('');
    // Sem destino ainda: o controle se declara inativo em vez de levar
    // para uma tela que não é de notificação.
    expect(sino).toHaveAttribute('aria-disabled', 'true');
    expect(sino).toHaveAttribute('title', 'Notificações — em breve');
  });

  it('mostra o badge quando o contador chega', () => {
    flagState.notificacoes = true;
    renderHeader({ notificationCount: 3 });

    expect(screen.getByRole('button', { name: 'Notificações' })).toHaveTextContent('3');
  });

  it('estoura o badge em 99+ em vez de esticar o header', () => {
    flagState.notificacoes = true;
    renderHeader({ notificationCount: 137 });

    expect(screen.getByRole('button', { name: 'Notificações' })).toHaveTextContent('99+');
  });

  it('contagem zero não vira badge "0"', () => {
    flagState.notificacoes = true;
    renderHeader({ notificationCount: 0 });

    expect(screen.getByRole('button', { name: 'Notificações' })).toHaveTextContent('');
  });
});
