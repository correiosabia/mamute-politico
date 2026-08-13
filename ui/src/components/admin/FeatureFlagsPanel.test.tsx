import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fetchFeatureFlagsAdmin, saveFeatureFlag } from '@/api/admin';
import { FeatureFlagsPanel } from './FeatureFlagsPanel';

vi.mock('@/api/admin', () => ({
  fetchFeatureFlagsAdmin: vi.fn(),
  saveFeatureFlag: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FeatureFlagsPanel />
    </QueryClientProvider>
  );
}

describe('FeatureFlagsPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lista a flag do registro mesmo sem linha no banco, como off', async () => {
    vi.mocked(fetchFeatureFlagsAdmin).mockResolvedValue([]);
    renderPanel();
    const select = (await screen.findByLabelText(
      /Aba Trajetória/i
    )) as HTMLSelectElement;
    expect(select.value).toBe('off');
  });

  it('usa o estado vindo do banco quando existe', async () => {
    vi.mocked(fetchFeatureFlagsAdmin).mockResolvedValue([
      {
        key: 'trajetoria',
        state: 'admins',
        updated_at: null,
        tiers_ligados: 0,
        tiers_total: 3,
      },
    ]);
    renderPanel();
    const select = (await screen.findByLabelText(
      /Aba Trajetória/i
    )) as HTMLSelectElement;
    expect(select.value).toBe('admins');
  });

  it('NAO lista linha do banco que nao esta no registro do codigo', async () => {
    // Esta é a propriedade central do desenho: apagar a flag do código a faz
    // sumir do controle, sem segundo mecanismo para esconder o botão.
    vi.mocked(fetchFeatureFlagsAdmin).mockResolvedValue([
      {
        key: 'trajetoria',
        state: 'off',
        updated_at: null,
        tiers_ligados: 0,
        tiers_total: 3,
      },
      {
        key: 'flag_removida_do_codigo',
        state: 'all',
        updated_at: null,
        tiers_ligados: 2,
        tiers_total: 3,
      },
    ]);
    renderPanel();
    await screen.findByLabelText(/Aba Trajetória/i);
    expect(
      screen.queryByText(/flag_removida_do_codigo/i)
    ).not.toBeInTheDocument();
  });

  it('denuncia flag liberada que nenhum plano libera', async () => {
    vi.mocked(fetchFeatureFlagsAdmin).mockResolvedValue([
      {
        key: 'trajetoria',
        state: 'all',
        updated_at: null,
        tiers_ligados: 0,
        tiers_total: 3,
      },
    ]);
    renderPanel();
    expect(
      await screen.findByText(/Nenhum plano libera esta funcionalidade/i)
    ).toBeInTheDocument();
  });

  it('mostra em quantos planos esta liberada', async () => {
    vi.mocked(fetchFeatureFlagsAdmin).mockResolvedValue([
      {
        key: 'trajetoria',
        state: 'all',
        updated_at: null,
        tiers_ligados: 2,
        tiers_total: 3,
      },
    ]);
    renderPanel();
    expect(
      await screen.findByText(/Liberada em 2 de 3 planos/i)
    ).toBeInTheDocument();
  });

  it('salva ao trocar o estado', async () => {
    vi.mocked(fetchFeatureFlagsAdmin).mockResolvedValue([]);
    vi.mocked(saveFeatureFlag).mockResolvedValue({
      key: 'trajetoria',
      state: 'all',
      updated_at: null,
      tiers_ligados: 0,
      tiers_total: 3,
    });
    renderPanel();
    const select = await screen.findByLabelText(/Aba Trajetória/i);
    fireEvent.change(select, { target: { value: 'all' } });
    await waitFor(() =>
      expect(vi.mocked(saveFeatureFlag)).toHaveBeenCalledWith(
        'trajetoria',
        'all'
      )
    );
  });
});
