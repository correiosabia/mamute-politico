import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type * as endpointsModule from '@/api/endpoints';

const flagState: Record<string, boolean> = {
  marcacoes_pessoais: false,
  mamutometro: false,
  trajetoria: false,
};

vi.mock('@/hooks/useFeatureFlag', () => ({
  useFeatureFlag: (key: string) => flagState[key] === true,
}));
vi.mock('@/components/layout/Header', () => ({ Header: () => <header /> }));
vi.mock('@/components/selecao/SelecaoFooter', () => ({
  SelecaoFooter: () => <footer />,
}));
vi.mock('@/components/dashboard/WordCloud', () => ({ WordCloud: () => <div /> }));
vi.mock('@/components/dashboard/ProposicoesList', () => ({
  ProposicoesList: () => <div />,
}));
vi.mock('@/components/dashboard/VotacoesTable', () => ({
  VotacoesTable: () => <div />,
}));
vi.mock('@/components/dashboard/ProposicoesTable', () => ({
  ProposicoesTable: () => <div />,
}));
vi.mock('@/components/dashboard/TaquigraficasTable', () => ({
  TaquigraficasTable: () => <div />,
}));
vi.mock('@/components/dashboard/EmendasTable', () => ({
  EmendasTable: () => <div />,
}));

const marcacoesSettings = {
  mamutometro: {
    enabled: true,
    max_level: 3,
    notice_text: 'Aviso neutro.',
    escopo: 'monitorados' as const,
    limit: null,
    used: 0,
  },
  tags: { escopo: 'todos' as const },
};

vi.mock('@/api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof endpointsModule>()),
  getParliamentarian: vi.fn().mockResolvedValue({
    id: 7,
    name: 'Alan Rick',
    type: 'Deputado',
    party: 'UNIÃO',
    state_elected: 'AC',
    parliamentarian_code: 777,
  }),
  listMyProjectFavorites: vi.fn().mockResolvedValue([
    { id: 1, projeto_id: 10, parliamentarian_id: 7, position: 0, created_at: '', updated_at: '' },
  ]),
  getMyParliamentarianDashboardStats: vi.fn().mockResolvedValue({}),
  getAmendmentsSummary: vi.fn().mockResolvedValue({}),
  sendSectionView: vi.fn(),
  getMarcacoesSettings: vi.fn().mockResolvedValue(marcacoesSettings),
  listMyProjectTags: vi.fn().mockResolvedValue([]),
  listMyParliamentarianTags: vi.fn().mockResolvedValue([]),
  listMyMamutometro: vi.fn().mockResolvedValue([]),
}));

async function renderPerfil() {
  const { default: ParlamentarDashboard } = await import('./ParlamentarDashboard');
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/parlamentar/7']}>
        <Routes>
          <Route path="/parlamentar/:id" element={<ParlamentarDashboard />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ParlamentarDashboard — seção "Suas marcações"', () => {
  beforeEach(() => {
    flagState.marcacoes_pessoais = false;
    flagState.mamutometro = false;
  });

  it('com as flags desligadas, a seção não existe', async () => {
    await renderPerfil();

    await screen.findByText('Dados cadastrais');
    expect(screen.queryByText('Suas marcações')).not.toBeInTheDocument();
  });

  it('monitorado + flags ligadas: seção com escala e editor de tags', async () => {
    flagState.marcacoes_pessoais = true;
    flagState.mamutometro = true;
    await renderPerfil();

    await waitFor(() => {
      expect(screen.getByText('Suas marcações')).toBeInTheDocument();
      expect(
        screen.getByRole('group', { name: /Mamutômetro de Alan Rick/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: /Editar tags de Alan Rick/i }),
      ).toBeInTheDocument();
    });
  });

  it('NÃO monitorado + escopo `monitorados`: esconde a escala, mantém tags (escopo `todos`)', async () => {
    flagState.marcacoes_pessoais = true;
    flagState.mamutometro = true;
    const endpoints = await import('@/api/endpoints');
    vi.mocked(endpoints.listMyProjectFavorites).mockResolvedValue([]);
    await renderPerfil();

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Editar tags de Alan Rick/i }),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByRole('group', { name: /Mamutômetro de Alan Rick/i }),
    ).not.toBeInTheDocument();
  });
});
