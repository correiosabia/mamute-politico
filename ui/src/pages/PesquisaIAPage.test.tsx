import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getChatbotQuota, streamChat } from '@/api/chatbot';
import PesquisaIAPage from './PesquisaIAPage';

vi.mock('@/components/layout/Header', () => ({
  Header: () => null,
}));

vi.mock('@/api/chatbot', () => ({
  ChatbotStreamError: class ChatbotStreamError extends Error {},
  getChatbotQuota: vi.fn(),
  streamChat: vi.fn(),
}));

const mockedGetChatbotQuota = vi.mocked(getChatbotQuota);
const mockedStreamChat = vi.mocked(streamChat);

function renderPage(initialEntry: string) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/pesquisa" element={<PesquisaIAPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('PesquisaIAPage URL question import', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetChatbotQuota.mockResolvedValue({
      enabled: false,
      limit: null,
      used: 0,
      remaining: null,
      reset_at: '2026-06-01T00:00:00Z',
      limit_reached: false,
    });
    mockedStreamChat.mockResolvedValue(undefined);
  });

  it('fills the question from the URL without auto-sending it', async () => {
    renderPage('/pesquisa?autoSend=1&pergunta=Quem%20discursou%20sobre%20educacao%3F');

    const input = await screen.findByPlaceholderText(
      'Digite sua pergunta sobre dados legislativos...'
    );

    await waitFor(() => {
      expect(input).toHaveValue('Quem discursou sobre educacao?');
    });
    expect(mockedStreamChat).not.toHaveBeenCalled();
  });
});

describe('PesquisaIAPage empty stream handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetChatbotQuota.mockResolvedValue({
      enabled: false,
      limit: null,
      used: 0,
      remaining: null,
      reset_at: '2026-06-01T00:00:00Z',
      limit_reached: false,
    });
  });

  it('shows a fallback message when the stream ends without tokens', async () => {
    // Bug de prod (02/08/2026): stream fechava sem nenhum token e a bolha
    // ficava eternamente no indicador de digitação, sem erro nenhum.
    mockedStreamChat.mockResolvedValue(undefined);
    renderPage('/pesquisa');

    const input = await screen.findByPlaceholderText(
      'Digite sua pergunta sobre dados legislativos...'
    );
    fireEvent.change(input, { target: { value: 'O que diz o parlamentar X sobre greve?' } });
    fireEvent.click(screen.getByRole('button', { name: /enviar/i }));

    await waitFor(() => {
      expect(mockedStreamChat).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(
        screen.getByText(/Não consegui gerar uma resposta agora/)
      ).toBeInTheDocument();
    });
  });

  it('keeps the streamed answer when tokens arrive', async () => {
    mockedStreamChat.mockImplementation(async ({ onToken }) => {
      onToken('Resposta ');
      onToken('completa.');
    });
    renderPage('/pesquisa');

    const input = await screen.findByPlaceholderText(
      'Digite sua pergunta sobre dados legislativos...'
    );
    fireEvent.change(input, { target: { value: 'Pergunta qualquer' } });
    fireEvent.click(screen.getByRole('button', { name: /enviar/i }));

    await waitFor(() => {
      expect(screen.getByText('Resposta completa.')).toBeInTheDocument();
    });
    expect(screen.queryByText(/Não consegui gerar uma resposta agora/)).toBeNull();
  });
});
