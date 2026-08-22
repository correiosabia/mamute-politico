import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fetchFeatureFlags } from '@/api/endpoints';
import { RequireFeature } from './App';

vi.mock('@/api/endpoints', () => ({ fetchFeatureFlags: vi.fn() }));

function renderRota() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/candidaturas']}>
        <Routes>
          <Route
            path="/candidaturas"
            element={
              <RequireFeature flag="busca_candidaturas">
                <div>TELA_CANDIDATURAS</div>
              </RequireFeature>
            }
          />
          <Route path="/" element={<div>INICIO_STUB</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('RequireFeature — portão de rota por feature flag', () => {
  beforeEach(() => {
    vi.mocked(fetchFeatureFlags).mockReset();
  });

  it('feature nova nasce inacessível: chave ausente vale off', async () => {
    // Sem linha no banco a chave não vem na resposta — é assim que a feature
    // nasce desligada sem migration.
    vi.mocked(fetchFeatureFlags).mockResolvedValue({});
    renderRota();

    expect(await screen.findByText('INICIO_STUB')).toBeInTheDocument();
    expect(screen.queryByText('TELA_CANDIDATURAS')).not.toBeInTheDocument();
  });

  it('não expulsa ninguém enquanto as flags carregam', () => {
    vi.mocked(fetchFeatureFlags).mockReturnValue(new Promise(() => {}));
    renderRota();

    // Nem monta a tela nem redireciona: decidir antes da resposta chutaria
    // justamente quem tem acesso.
    expect(screen.queryByText('TELA_CANDIDATURAS')).not.toBeInTheDocument();
    expect(screen.queryByText('INICIO_STUB')).not.toBeInTheDocument();
  });

  it('monta a tela quando a flag está liberada para o chamador', async () => {
    vi.mocked(fetchFeatureFlags).mockResolvedValue({
      busca_candidaturas: 'liberada',
    });
    renderRota();

    expect(await screen.findByText('TELA_CANDIDATURAS')).toBeInTheDocument();
  });

  it('cadeado não abre a tela: a prévia desfocada desta tela não existe', async () => {
    vi.mocked(fetchFeatureFlags).mockResolvedValue({
      busca_candidaturas: 'bloqueada',
    });
    renderRota();

    expect(await screen.findByText('INICIO_STUB')).toBeInTheDocument();
    expect(screen.queryByText('TELA_CANDIDATURAS')).not.toBeInTheDocument();
  });
});
