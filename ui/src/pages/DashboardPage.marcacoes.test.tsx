import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type * as endpointsModule from '@/api/endpoints';

const flagState: Record<string, boolean> = {
  marcacoes_pessoais: false,
  mamutometro: false,
};

vi.mock('@/hooks/useFeatureFlag', () => ({
  useFeatureFlag: (key: string) => flagState[key] === true,
}));
vi.mock('@/components/layout/Header', () => ({ Header: () => <header /> }));

const PARLAMENTARES = [
  { id: 1, name: 'Alan Rick', type: 'Deputado', party: 'UNIÃO', state_elected: 'AC' },
];

vi.mock('@/api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof endpointsModule>()),
  listMyProjectFavorites: vi.fn().mockResolvedValue([
    { id: 1, projeto_id: 10, parliamentarian_id: 1, position: 0, created_at: '', updated_at: '' },
  ]),
  getParliamentarian: vi
    .fn()
    .mockImplementation((id: number) =>
      Promise.resolve(PARLAMENTARES.find((p) => p.id === id)),
    ),
  getMyDashboardActivity: vi.fn().mockResolvedValue({ propositions: [], votes: [] }),
  getMarcacoesSettings: vi.fn().mockResolvedValue({
    mamutometro: {
      enabled: true,
      max_level: 3,
      notice_text: 'Aviso neutro.',
      escopo: 'monitorados',
      limit: null,
      used: 0,
    },
    tags: { escopo: 'todos' },
  }),
  listMyProjectTags: vi.fn().mockResolvedValue([]),
  listMyParliamentarianTags: vi.fn().mockResolvedValue([]),
  listMyMamutometro: vi.fn().mockResolvedValue([]),
}));

async function renderDashboard() {
  const { default: DashboardPage } = await import('./DashboardPage');
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/dashboard']}>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DashboardPage — marcações pessoais nos cards de monitorados', () => {
  beforeEach(() => {
    flagState.marcacoes_pessoais = false;
    flagState.mamutometro = false;
  });

  it('com as flags desligadas, o card fica idêntico ao de antes da feature', async () => {
    await renderDashboard();

    await screen.findByText('Alan Rick');
    expect(
      screen.queryByRole('group', { name: /Mamutômetro de Alan Rick/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Editar tags de Alan Rick/i }),
    ).not.toBeInTheDocument();
  });

  it('com flag global + plano liberado, escala e editor de tags aparecem no card', async () => {
    flagState.marcacoes_pessoais = true;
    flagState.mamutometro = true;
    await renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByRole('group', { name: /Mamutômetro de Alan Rick/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: /Editar tags de Alan Rick/i }),
      ).toBeInTheDocument();
    });
  });

  it('flag global ligada mas plano sem a feature: escala não aparece', async () => {
    flagState.mamutometro = true;
    const endpoints = await import('@/api/endpoints');
    vi.mocked(endpoints.getMarcacoesSettings).mockResolvedValueOnce({
      mamutometro: {
        enabled: false, // plano do assinante não cobre — resolvido pelo backend
        max_level: 3,
        notice_text: 'Aviso neutro.',
        escopo: 'monitorados',
        limit: null,
        used: 0,
      },
      tags: { escopo: 'todos' },
    });
    await renderDashboard();

    await screen.findByText('Alan Rick');
    expect(
      screen.queryByRole('group', { name: /Mamutômetro de Alan Rick/i }),
    ).not.toBeInTheDocument();
  });
});
