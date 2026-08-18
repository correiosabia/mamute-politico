import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fetchTierFeatures, saveTierFeatures } from '@/api/admin';
import { TierFeaturesFields } from './TierFeaturesFields';

vi.mock('@/api/admin', () => ({
  fetchTierFeatures: vi.fn(),
  saveTierFeatures: vi.fn(),
}));

function renderFields(props: { disabled?: boolean } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TierFeaturesFields tierId={1} {...props} />
    </QueryClientProvider>
  );
}

describe('TierFeaturesFields', () => {
  beforeEach(() => vi.clearAllMocks());

  it('plano sem nenhuma feature nasce com tudo oculto', async () => {
    vi.mocked(fetchTierFeatures).mockResolvedValue({
      tier_id: 1,
      features: {},
    });
    renderFields();
    const select = (await screen.findByLabelText(
      /Aba Trajetória/i
    )) as HTMLSelectElement;
    expect(select.value).toBe('oculto');
  });

  it('mostra o modo que o plano ja tem', async () => {
    vi.mocked(fetchTierFeatures).mockResolvedValue({
      tier_id: 1,
      features: { trajetoria: 'cadeado' },
    });
    renderFields();
    const select = (await screen.findByLabelText(
      /Aba Trajetória/i
    )) as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe('cadeado'));
  });

  it('salva o mapa completo ao selecionar um modo', async () => {
    vi.mocked(fetchTierFeatures).mockResolvedValue({
      tier_id: 1,
      features: {},
    });
    vi.mocked(saveTierFeatures).mockResolvedValue({
      tier_id: 1,
      features: { emendas: 'cadeado' },
    });
    renderFields();
    const select = await screen.findByLabelText(/Aba Emendas/i);
    fireEvent.change(select, { target: { value: 'cadeado' } });
    await waitFor(() =>
      expect(vi.mocked(saveTierFeatures)).toHaveBeenCalledWith(1, {
        emendas: 'cadeado',
      })
    );
  });

  it('voltar para oculto tira a chave do mapa', async () => {
    vi.mocked(fetchTierFeatures).mockResolvedValue({
      tier_id: 1,
      features: { trajetoria: 'liberado' },
    });
    vi.mocked(saveTierFeatures).mockResolvedValue({
      tier_id: 1,
      features: {},
    });
    renderFields();
    const select = (await screen.findByLabelText(
      /Aba Trajetória/i
    )) as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe('liberado'));
    fireEvent.change(select, { target: { value: 'oculto' } });
    await waitFor(() =>
      expect(vi.mocked(saveTierFeatures)).toHaveBeenCalledWith(1, {})
    );
  });

  it('plano fora do ar nao aceita edicao', async () => {
    vi.mocked(fetchTierFeatures).mockResolvedValue({
      tier_id: 1,
      features: {},
    });
    renderFields({ disabled: true });
    const select = (await screen.findByLabelText(
      /Aba Trajetória/i
    )) as HTMLSelectElement;
    expect(select.disabled).toBe(true);
  });
});
