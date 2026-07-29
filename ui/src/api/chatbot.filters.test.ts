import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { streamChat } from './chatbot';

/**
 * A nuvem de palavras monta perguntas do tipo "O que diz o(a) parlamentar X
 * sobre Y". Sem mandar o parlamentar como filtro, a busca vetorial procura o
 * tema em toda a base e devolve trechos de qualquer um — foi assim que o
 * chatbot respondeu que não tinha informação sobre o Flávio Bolsonaro.
 */

function emptyStreamResponse(): Response {
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('data: {"type":"end"}\n\n'));
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

function requestBody(): Record<string, unknown> {
  const call = vi.mocked(global.fetch).mock.calls[0];
  return JSON.parse((call[1] as RequestInit).body as string);
}

describe('streamChat filters', () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue(emptyStreamResponse());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('envia o parlamentar como filtro quando informado', async () => {
    await streamChat({
      question: 'O que diz o(a) parlamentar Flávio Bolsonaro sobre Banco',
      history: [],
      filters: { parliamentarian_ids: [544] },
      onToken: () => {},
    });

    expect(requestBody().filters).toEqual({ parliamentarian_ids: [544] });
  });

  it('omite o campo filters quando não há filtro', async () => {
    await streamChat({
      question: 'Quais projetos sobre educação?',
      history: [],
      onToken: () => {},
    });

    expect(requestBody()).not.toHaveProperty('filters');
  });

  it('mantém pergunta e histórico no corpo', async () => {
    await streamChat({
      question: 'Pergunta',
      history: [{ role: 'user', content: 'anterior' }],
      filters: { parliamentarian_ids: [1] },
      onToken: () => {},
    });

    const body = requestBody();
    expect(body.question).toBe('Pergunta');
    expect(body.history).toEqual([{ role: 'user', content: 'anterior' }]);
  });
});
