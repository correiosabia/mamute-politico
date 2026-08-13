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

  it('plano sem nenhuma feature liberada nasce com tudo desmarcado', async () => {
    vi.mocked(fetchTierFeatures).mockResolvedValue({
      tier_id: 1,
      features: [],
    });
    renderFields();
    const box = (await screen.findByLabelText(
      /Aba Trajetória/i
    )) as HTMLInputElement;
    expect(box.checked).toBe(false);
  });

  it('marca o que o plano ja libera', async () => {
    vi.mocked(fetchTierFeatures).mockResolvedValue({
      tier_id: 1,
      features: ['trajetoria'],
    });
    renderFields();
    const box = (await screen.findByLabelText(
      /Aba Trajetória/i
    )) as HTMLInputElement;
    await waitFor(() => expect(box.checked).toBe(true));
  });

  it('salva a lista completa ao marcar', async () => {
    vi.mocked(fetchTierFeatures).mockResolvedValue({
      tier_id: 1,
      features: [],
    });
    vi.mocked(saveTierFeatures).mockResolvedValue({
      tier_id: 1,
      features: ['trajetoria'],
    });
    renderFields();
    const box = await screen.findByLabelText(/Aba Trajetória/i);
    fireEvent.click(box);
    await waitFor(() =>
      expect(vi.mocked(saveTierFeatures)).toHaveBeenCalledWith(1, [
        'trajetoria',
      ])
    );
  });

  it('salva lista vazia ao desmarcar', async () => {
    vi.mocked(fetchTierFeatures).mockResolvedValue({
      tier_id: 1,
      features: ['trajetoria'],
    });
    vi.mocked(saveTierFeatures).mockResolvedValue({
      tier_id: 1,
      features: [],
    });
    renderFields();
    const box = (await screen.findByLabelText(
      /Aba Trajetória/i
    )) as HTMLInputElement;
    await waitFor(() => expect(box.checked).toBe(true));
    fireEvent.click(box);
    await waitFor(() =>
      expect(vi.mocked(saveTierFeatures)).toHaveBeenCalledWith(1, [])
    );
  });

  it('plano fora do ar nao aceita edicao', async () => {
    vi.mocked(fetchTierFeatures).mockResolvedValue({
      tier_id: 1,
      features: [],
    });
    renderFields({ disabled: true });
    const box = (await screen.findByLabelText(
      /Aba Trajetória/i
    )) as HTMLInputElement;
    expect(box.disabled).toBe(true);
  });
});
