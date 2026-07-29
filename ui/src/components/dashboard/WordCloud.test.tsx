import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { listParliamentarianSpeechAnalysis } from '@/api/endpoints';
import { WordCloud } from './WordCloud';

/**
 * O clique num termo da nuvem monta a pergunta da Pesquisa IA. O id do
 * parlamentar precisa viajar junto: é ele que vira filtro da busca vetorial do
 * outro lado.
 */

const navigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigate };
});

vi.mock('@/api/endpoints', () => ({
  listParliamentarianSpeechAnalysis: vi.fn(),
}));

const mockedList = vi.mocked(listParliamentarianSpeechAnalysis);

function renderCloud() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <WordCloud parliamentarianId={544} parlamentarNome="Flávio Bolsonaro" />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('WordCloud — navegação para a Pesquisa IA', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedList.mockResolvedValue([
      {
        primary_keyword: { term: 'banco', frequency: 42, rank: 1 },
      },
      {
        primary_keyword: { term: 'segurança pública', frequency: 10, rank: 2 },
      },
    ] as never);
  });

  it('leva o id do parlamentar na URL da pergunta', async () => {
    renderCloud();

    const termo = await screen.findByText(/banco/i);
    fireEvent.click(termo);

    await waitFor(() => expect(navigate).toHaveBeenCalled());
    const destino = navigate.mock.calls[0][0] as { pathname: string; search: string };
    const params = new URLSearchParams(destino.search);

    expect(destino.pathname).toBe('/pesquisa');
    expect(params.get('parlamentarId')).toBe('544');
  });

  it('mantém a pergunta e o autoSend', async () => {
    renderCloud();

    fireEvent.click(await screen.findByText(/banco/i));

    await waitFor(() => expect(navigate).toHaveBeenCalled());
    const destino = navigate.mock.calls[0][0] as { search: string };
    const params = new URLSearchParams(destino.search);

    expect(params.get('autoSend')).toBe('1');
    expect(params.get('pergunta')).toBe(
      'O que diz o(a) parlamentar Flávio Bolsonaro sobre Banco'
    );
  });
});
