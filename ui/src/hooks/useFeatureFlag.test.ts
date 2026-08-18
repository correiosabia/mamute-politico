import { describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import { fetchFeatureFlags } from '@/api/endpoints';
import { useFeatureFlag } from './useFeatureFlag';

vi.mock('@/api/endpoints', () => ({ fetchFeatureFlags: vi.fn() }));

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return React.createElement(QueryClientProvider, { client }, children);
}

describe('useFeatureFlag', () => {
  it('devolve false enquanto carrega', () => {
    vi.mocked(fetchFeatureFlags).mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useFeatureFlag('trajetoria'), {
      wrapper,
    });
    expect(result.current).toBe(false);
  });

  it('devolve true quando a flag esta liberada para o chamador', async () => {
    vi.mocked(fetchFeatureFlags).mockResolvedValue({ trajetoria: 'liberada' });
    const { result } = renderHook(() => useFeatureFlag('trajetoria'), {
      wrapper,
    });
    await waitFor(() => expect(result.current).toBe(true));
  });

  it('devolve false quando a flag esta bloqueada (cadeado nao e acesso)', async () => {
    vi.mocked(fetchFeatureFlags).mockResolvedValue({ trajetoria: 'bloqueada' });
    const { result } = renderHook(() => useFeatureFlag('trajetoria'), {
      wrapper,
    });
    await waitFor(() =>
      expect(vi.mocked(fetchFeatureFlags)).toHaveBeenCalled()
    );
    expect(result.current).toBe(false);
  });

  it('devolve false quando a chave nao veio na resposta', async () => {
    // Chave sem linha no banco: a ausencia vale `off`.
    vi.mocked(fetchFeatureFlags).mockResolvedValue({});
    const { result } = renderHook(() => useFeatureFlag('trajetoria'), {
      wrapper,
    });
    await waitFor(() =>
      expect(vi.mocked(fetchFeatureFlags)).toHaveBeenCalled()
    );
    expect(result.current).toBe(false);
  });

  it('devolve false quando a requisicao falha', async () => {
    vi.mocked(fetchFeatureFlags).mockRejectedValue(new Error('rede'));
    const { result } = renderHook(() => useFeatureFlag('trajetoria'), {
      wrapper,
    });
    await waitFor(() =>
      expect(vi.mocked(fetchFeatureFlags)).toHaveBeenCalled()
    );
    expect(result.current).toBe(false);
  });
});
