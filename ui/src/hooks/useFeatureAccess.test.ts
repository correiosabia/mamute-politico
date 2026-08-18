import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import { fetchFeatureFlags } from '@/api/endpoints';
import { toggleFeaturePreview } from '@/lib/featurePreview';
import { useFeatureAccess } from './useFeatureAccess';

vi.mock('@/api/endpoints', () => ({ fetchFeatureFlags: vi.fn() }));

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return React.createElement(QueryClientProvider, { client }, children);
}

describe('useFeatureAccess', () => {
  beforeEach(() => localStorage.clear());

  it('devolve o valor resolvido da API', async () => {
    vi.mocked(fetchFeatureFlags).mockResolvedValue({ emendas: 'bloqueada' });
    const { result } = renderHook(() => useFeatureAccess('emendas'), {
      wrapper,
    });
    await waitFor(() => expect(result.current).toBe('bloqueada'));
  });

  it('liberada passa direto', async () => {
    vi.mocked(fetchFeatureFlags).mockResolvedValue({ emendas: 'liberada' });
    const { result } = renderHook(() => useFeatureAccess('emendas'), {
      wrapper,
    });
    await waitFor(() => expect(result.current).toBe('liberada'));
  });

  it('chave ausente vale oculta', async () => {
    vi.mocked(fetchFeatureFlags).mockResolvedValue({});
    const { result } = renderHook(() => useFeatureAccess('emendas'), {
      wrapper,
    });
    await waitFor(() =>
      expect(vi.mocked(fetchFeatureFlags)).toHaveBeenCalled()
    );
    expect(result.current).toBe('oculta');
  });

  it('erro de rede vale oculta (falha fechado)', async () => {
    vi.mocked(fetchFeatureFlags).mockRejectedValue(new Error('rede'));
    const { result } = renderHook(() => useFeatureAccess('emendas'), {
      wrapper,
    });
    await waitFor(() =>
      expect(vi.mocked(fetchFeatureFlags)).toHaveBeenCalled()
    );
    expect(result.current).toBe('oculta');
  });

  it('preview de admin degrada liberada para bloqueada', async () => {
    vi.mocked(fetchFeatureFlags).mockResolvedValue({ emendas: 'liberada' });
    toggleFeaturePreview('emendas');
    const { result } = renderHook(() => useFeatureAccess('emendas'), {
      wrapper,
    });
    await waitFor(() => expect(result.current).toBe('bloqueada'));
  });

  it('preview nunca revela o que esta oculto', async () => {
    vi.mocked(fetchFeatureFlags).mockResolvedValue({});
    toggleFeaturePreview('emendas');
    const { result } = renderHook(() => useFeatureAccess('emendas'), {
      wrapper,
    });
    await waitFor(() =>
      expect(vi.mocked(fetchFeatureFlags)).toHaveBeenCalled()
    );
    expect(result.current).toBe('oculta');
  });
});
