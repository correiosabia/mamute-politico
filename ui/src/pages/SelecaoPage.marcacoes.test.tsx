import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type * as endpointsModule from '@/api/endpoints';

const flagState: Record<string, boolean> = { marcacoes_pessoais: false };

vi.mock('@/hooks/useFeatureFlag', () => ({
  useFeatureFlag: (key: string) => flagState[key] === true,
}));
vi.mock('@/components/layout/Header', () => ({ Header: () => <header /> }));
vi.mock('@/components/selecao/SelecaoFooter', () => ({
  SelecaoFooter: () => <footer />,
}));

const PARLAMENTARES = [
  { id: 1, name: 'Alan Rick', type: 'Deputado', party: 'UNIÃO', state_elected: 'AC' },
  { id: 2, name: 'Beatriz Souza', type: 'Deputado', party: 'PT', state_elected: 'SP' },
];

vi.mock('@/api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof endpointsModule>()),
  listMyProjectFavorites: vi.fn().mockResolvedValue([
    { id: 1, projeto_id: 10, parliamentarian_id: 1, position: 0, created_at: '', updated_at: '' },
    { id: 2, projeto_id: 10, parliamentarian_id: 2, position: 1, created_at: '', updated_at: '' },
  ]),
  getMyProjectFavoritesQuota: vi.fn().mockResolvedValue({
    limit: 10,
    used: 2,
    remaining: 8,
    limit_reached: false,
    unlimited: false,
    camara: { used: 2, limit: 10, limit_reached: false },
    senado: { used: 0, limit: 10, limit_reached: false },
  }),
  getParliamentarian: vi
    .fn()
    .mockImplementation((id: number) =>
      Promise.resolve(PARLAMENTARES.find((p) => p.id === id)),
    ),
  listParliamentarians: vi.fn().mockResolvedValue([]),
  getParliamentarianCatalogConfig: vi.fn().mockResolvedValue({
    allowed_situations: ['exercicio'],
    default_situacao: 'exercicio',
  }),
  reorderMyProjectFavorites: vi.fn(),
}));

class MockIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

async function renderSelecao() {
  const { default: SelecaoPage } = await import('./SelecaoPage');
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/selecao#camara-dos-deputados']}>
        <SelecaoPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SelecaoPage — portão da flag marcacoes_pessoais', () => {
  beforeEach(() => {
    vi.stubGlobal('IntersectionObserver', MockIntersectionObserver);
    flagState.marcacoes_pessoais = false;
  });

  it('com a flag desligada, não renderiza os controles de ordem', async () => {
    await renderSelecao();

    await screen.findByText('Alan Rick');
    expect(
      screen.queryByRole('button', { name: /Mover .* para cima/i }),
    ).not.toBeInTheDocument();
  });

  it('com a flag ligada, renderiza os controles de ordem', async () => {
    flagState.marcacoes_pessoais = true;
    await renderSelecao();

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Mover Beatriz Souza para cima/i }),
      ).toBeInTheDocument();
    });
  });
});
