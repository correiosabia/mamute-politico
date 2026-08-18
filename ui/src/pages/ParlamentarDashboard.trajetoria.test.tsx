import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type * as endpointsModule from '@/api/endpoints';

const isAdminState = { isAdmin: false, isLoading: false };
// Acesso resolvido por chave; default espelha a producao de hoje: emendas
// liberada (seed da migration) e trajetoria oculta para nao-admin.
const accessState: Record<string, string> = {
  trajetoria: 'oculta',
  emendas: 'liberada',
};

vi.mock('@/hooks/useIsAdmin', () => ({ useIsAdmin: () => isAdminState }));
vi.mock('@/hooks/useFeatureAccess', () => ({
  useFeatureAccess: (key: string) => accessState[key] ?? 'oculta',
}));
vi.mock('@/components/layout/Header', () => ({ Header: () => <header /> }));
vi.mock('@/components/selecao/SelecaoFooter', () => ({
  SelecaoFooter: () => <footer />,
}));
vi.mock('@/components/dashboard/WordCloud', () => ({
  WordCloud: () => <div />,
}));
vi.mock('@/components/dashboard/ProposicoesList', () => ({
  ProposicoesList: () => <div />,
}));
vi.mock('@/api/events', () => ({
  sendSectionView: vi.fn(),
  sendPageView: vi.fn(),
}));
vi.mock('@/api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof endpointsModule>()),
  getParliamentarian: vi.fn().mockResolvedValue({
    id: 1,
    parliamentarian_code: 123,
    name: 'Sergio Moro',
    full_name: 'Sergio Fernando Moro',
    party: 'PL',
    state_elected: 'PR',
    type: 'Senador',
  }),
  listMyProjectFavorites: vi.fn().mockResolvedValue([]),
  getMyParliamentarianDashboardStats: vi.fn().mockResolvedValue({
    propositions: 0,
    roll_call_votes: 0,
    speeches: 0,
  }),
  getAmendmentsSummary: vi.fn().mockResolvedValue({
    year: 2026,
    count: 0,
    committed_total: '0.00',
    paid_total: '0.00',
  }),
  listRollCallVotes: vi.fn().mockResolvedValue([]),
  getElectoralHistory: vi.fn().mockResolvedValue({ entries: [] }),
}));

import ParlamentarDashboard from './ParlamentarDashboard';

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/parlamentar/1']}>
        <Routes>
          <Route path="/parlamentar/:id" element={<ParlamentarDashboard />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('gate da aba Trajetória', () => {
  beforeEach(() => {
    isAdminState.isAdmin = false;
    accessState.trajetoria = 'oculta';
    accessState.emendas = 'liberada';
  });

  it('oculta esconde a aba', async () => {
    renderPage();
    await screen.findAllByText(/VOTAÇÕES/i);
    expect(screen.queryByText(/TRAJETÓRIA/i)).not.toBeInTheDocument();
  });

  it('liberada mostra a aba sem cadeado nem CTA', async () => {
    accessState.trajetoria = 'liberada';
    renderPage();
    await screen.findAllByText(/VOTAÇÕES/i);
    expect(screen.getByText(/TRAJETÓRIA/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/exclusivo para assinantes/i)
    ).not.toBeInTheDocument();
  });

  it('ser admin nao basta: quem manda agora e a resolucao', async () => {
    // O gate saiu do isAdmin improvisado. Admin continua vendo, mas via
    // resolucao da flag no backend, nao por checagem espalhada na tela.
    isAdminState.isAdmin = true;
    renderPage();
    await screen.findAllByText(/VOTAÇÕES/i);
    expect(screen.queryByText(/TRAJETÓRIA/i)).not.toBeInTheDocument();
  });
});

describe('estado bloqueado (cadeado + previa desfocada, CS-58)', () => {
  beforeEach(() => {
    isAdminState.isAdmin = false;
    accessState.trajetoria = 'bloqueada';
    accessState.emendas = 'bloqueada';
  });

  it('bloqueada mantem a aba na lista, com o conteudo sob CTA', async () => {
    renderPage();
    await screen.findAllByText(/VOTAÇÕES/i);
    expect(screen.getByRole('tab', { name: /TRAJETÓRIA/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /EMENDAS/i })).toBeInTheDocument();
    // O painel da aba ativa por padrao e VOTACOES; o CTA da aba bloqueada
    // monta ao clicar nela.
  });

  it('emendas bloqueada mostra cadeado no card de estatisticas', async () => {
    renderPage();
    await screen.findAllByText(/VOTAÇÕES/i);
    expect(
      await screen.findByText(/Exclusivo para assinantes/i)
    ).toBeInTheDocument();
  });
});
