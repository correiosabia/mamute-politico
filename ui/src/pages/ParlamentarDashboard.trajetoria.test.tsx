import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type * as endpointsModule from '@/api/endpoints';

const isAdminState = { isAdmin: false, isLoading: false };
const flagState: Record<string, boolean> = { trajetoria: false };

vi.mock('@/hooks/useIsAdmin', () => ({ useIsAdmin: () => isAdminState }));
vi.mock('@/hooks/useFeatureFlag', () => ({
  useFeatureFlag: (key: string) => flagState[key] === true,
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
    flagState.trajetoria = false;
  });

  it('flag desligada esconde a aba', async () => {
    renderPage();
    await screen.findAllByText(/VOTAÇÕES/i);
    expect(screen.queryByText(/TRAJETÓRIA/i)).not.toBeInTheDocument();
  });

  it('flag ligada mostra a aba', async () => {
    flagState.trajetoria = true;
    renderPage();
    await screen.findAllByText(/VOTAÇÕES/i);
    expect(screen.getByText(/TRAJETÓRIA/i)).toBeInTheDocument();
  });

  it('ser admin nao basta: quem manda agora e a flag', async () => {
    // O gate saiu do isAdmin improvisado. Admin continua vendo, mas via
    // resolucao da flag no backend, nao por checagem espalhada na tela.
    isAdminState.isAdmin = true;
    renderPage();
    await screen.findAllByText(/VOTAÇÕES/i);
    expect(screen.queryByText(/TRAJETÓRIA/i)).not.toBeInTheDocument();
  });
});
