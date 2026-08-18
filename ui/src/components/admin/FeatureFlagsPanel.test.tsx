import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fetchFeatureFlagsAdmin, saveFeatureFlag } from '@/api/admin';
import { FeatureFlagsPanel } from './FeatureFlagsPanel';
import { isFeaturePreviewOn } from '@/lib/featurePreview';

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
        tiers_liberados: 0,
        tiers_cadeado: 0,
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
        tiers_liberados: 0,
        tiers_cadeado: 0,
        tiers_total: 3,
      },
      {
        key: 'flag_removida_do_codigo',
        state: 'all',
        updated_at: null,
        tiers_liberados: 2,
        tiers_cadeado: 0,
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
        tiers_liberados: 0,
        tiers_cadeado: 0,
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
        tiers_liberados: 2,
        tiers_cadeado: 0,
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
      tiers_liberados: 0,
        tiers_cadeado: 0,
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

describe('FeatureFlagsPanel — cadeado e preview (CS-58)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('mostra a contagem de planos com cadeado', async () => {
    vi.mocked(fetchFeatureFlagsAdmin).mockResolvedValue([
      {
        key: 'trajetoria',
        state: 'all',
        updated_at: null,
        tiers_liberados: 1,
        tiers_cadeado: 2,
        tiers_total: 3,
      },
    ]);
    renderPanel();
    expect(
      await screen.findByText(/Liberada em 1 de 3 planos, com cadeado em 2/i)
    ).toBeInTheDocument();
  });

  it('alterna o preview "ver como bloqueada"', async () => {
    vi.mocked(fetchFeatureFlagsAdmin).mockResolvedValue([]);
    renderPanel();
    const botoes = await screen.findAllByTitle(/Ver como bloqueada/i);
    fireEvent.click(botoes[0]);
    expect(isFeaturePreviewOn('trajetoria')).toBe(true);
    const desligar = await screen.findByTitle(/Deixar de ver como bloqueada/i);
    fireEvent.click(desligar);
    expect(isFeaturePreviewOn('trajetoria')).toBe(false);
  });
});
