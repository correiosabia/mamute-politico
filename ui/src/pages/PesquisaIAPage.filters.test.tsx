import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getChatbotQuota, streamChat } from '@/api/chatbot';
import PesquisaIAPage from './PesquisaIAPage';

/**
 * Ao clicar num termo da nuvem, a pergunta chega aqui já nomeando o
 * parlamentar. Esse vínculo precisa virar filtro na chamada — o nome sozinho
 * dentro do texto da pergunta não restringe a busca vetorial.
 */

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
    defaultOptions: { queries: { retry: false } },
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

const PERGUNTA = 'O que diz o(a) parlamentar Flávio Bolsonaro sobre Banco';
const URL_NUVEM = `/pesquisa?autoSend=1&parlamentarId=544&pergunta=${encodeURIComponent(PERGUNTA)}`;

async function aguardarPreenchimento() {
  const input = await screen.findByPlaceholderText(
    'Digite sua pergunta sobre dados legislativos...'
  );
  await waitFor(() => expect(input).toHaveValue(PERGUNTA));
  return input;
}

function enviar() {
  fireEvent.click(screen.getByRole('button', { name: /enviar/i }));
}

describe('PesquisaIAPage — filtro vindo da nuvem de palavras', () => {
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

  it('envia o parlamentar como filtro na pergunta vinda da nuvem', async () => {
    renderPage(URL_NUVEM);
    await aguardarPreenchimento();

    enviar();

    await waitFor(() => expect(mockedStreamChat).toHaveBeenCalled());
    expect(mockedStreamChat.mock.calls[0][0]).toMatchObject({
      question: PERGUNTA,
      filters: { parliamentarian_ids: [544] },
    });
  });

  it('envia o tema estruturado quando presente na URL da nuvem', async () => {
    renderPage(`${URL_NUVEM}&tema=Banco`);
    await aguardarPreenchimento();

    enviar();

    await waitFor(() => expect(mockedStreamChat).toHaveBeenCalled());
    expect(mockedStreamChat.mock.calls[0][0]).toMatchObject({
      question: PERGUNTA,
      filters: { parliamentarian_ids: [544] },
      topic: 'Banco',
    });
  });

  it('descarta o tema junto com o filtro se a pergunta for reescrita', async () => {
    renderPage(`${URL_NUVEM}&tema=Banco`);
    const input = await aguardarPreenchimento();

    fireEvent.change(input, { target: { value: 'Quais projetos sobre educação?' } });
    enviar();

    await waitFor(() => expect(mockedStreamChat).toHaveBeenCalled());
    expect(mockedStreamChat.mock.calls[0][0]).not.toHaveProperty('topic');
    expect(mockedStreamChat.mock.calls[0][0]).not.toHaveProperty('filters');
  });

  it('descarta o filtro se o usuário reescrever a pergunta', async () => {
    renderPage(URL_NUVEM);
    const input = await aguardarPreenchimento();

    fireEvent.change(input, { target: { value: 'Quais projetos sobre educação?' } });
    enviar();

    await waitFor(() => expect(mockedStreamChat).toHaveBeenCalled());
    expect(mockedStreamChat.mock.calls[0][0]).not.toHaveProperty('filters');
  });

  it('não aplica o filtro numa segunda pergunta livre', async () => {
    renderPage(URL_NUVEM);
    const input = await aguardarPreenchimento();

    enviar();
    await waitFor(() => expect(mockedStreamChat).toHaveBeenCalledTimes(1));

    fireEvent.change(input, { target: { value: 'E sobre educação?' } });
    enviar();

    await waitFor(() => expect(mockedStreamChat).toHaveBeenCalledTimes(2));
    expect(mockedStreamChat.mock.calls[1][0]).not.toHaveProperty('filters');
  });

  it('pergunta digitada do zero não leva filtro', async () => {
    renderPage('/pesquisa');
    const input = await screen.findByPlaceholderText(
      'Digite sua pergunta sobre dados legislativos...'
    );

    fireEvent.change(input, { target: { value: 'Quem discursou sobre saúde?' } });
    enviar();

    await waitFor(() => expect(mockedStreamChat).toHaveBeenCalled());
    expect(mockedStreamChat.mock.calls[0][0]).not.toHaveProperty('filters');
  });
});
