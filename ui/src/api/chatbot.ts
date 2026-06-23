import { JWT_TOKEN_KEY } from '@/components/auth/config';

/** Client for Mamute Político chatbot (FastAPI); same-origin requests to `/chat/chatbot/*` (proxy routes /chat to the chatbot). */

export interface ChatMessagePayload {
  role: 'user' | 'assistant';
  content: string;
}

export interface StreamChatBody {
  question: string;
  history: ChatMessagePayload[];
}

export interface ChatbotQuota {
  enabled: boolean;
  limit: number | null;
  used: number;
  remaining: number | null;
  reset_at: string;
  limit_reached: boolean;
}

export class ChatbotStreamError extends Error {
  constructor(
    message: string,
    public status?: number
  ) {
    super(message);
    this.name = 'ChatbotStreamError';
  }
}

type SsePayload =
  | { type: 'token'; value: string }
  | { type: 'end' }
  | { type: 'error'; message: string }
  | { type: 'cancel' };

/** Relative URL; browser resolves against the page origin. */
export const CHATBOT_STREAM_PATH = '/chat/chatbot/stream';
export const CHATBOT_QUOTA_PATH = '/chat/chatbot/quota';

export function getChatbotStreamUrl(): string {
  return CHATBOT_STREAM_PATH;
}

function getChatbotToken(): string | undefined {
  if (typeof window === 'undefined') return undefined;
  return localStorage.getItem(JWT_TOKEN_KEY) ?? undefined;
}

function authHeaders(extra?: HeadersInit): HeadersInit {
  const headers: Record<string, string> = {
    ...(extra as Record<string, string> | undefined),
  };
  const token = getChatbotToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function parseErrorResponse(res: Response): Promise<string> {
  const text = await res.text();
  let message = text || res.statusText || `Erro ${res.status}`;
  try {
    const body = JSON.parse(text) as { detail?: unknown; message?: unknown };
    if (typeof body.detail === 'string') message = body.detail;
    else if (Array.isArray(body.detail)) {
      message = body.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join('; ');
    } else if (body.message != null) message = String(body.message);
  } catch {
    /* use message as text */
  }
  return message;
}

export async function getChatbotQuota(): Promise<ChatbotQuota> {
  const res = await fetch(CHATBOT_QUOTA_PATH, {
    method: 'GET',
    headers: authHeaders({ Accept: 'application/json' }),
  });
  if (!res.ok) {
    throw new ChatbotStreamError(await parseErrorResponse(res), res.status);
  }
  return res.json() as Promise<ChatbotQuota>;
}

export interface StreamChatOptions extends StreamChatBody {
  signal?: AbortSignal;
  onToken: (chunk: string) => void;
}

/**
 * POST stream endpoint; parses SSE `data: {...}` lines from the chatbot backend.
 */
export async function streamChat(options: StreamChatOptions): Promise<void> {
  const { question, history, signal, onToken } = options;

  const res = await fetch(getChatbotStreamUrl(), {
    method: 'POST',
    headers: authHeaders({
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    }),
    body: JSON.stringify({ question, history }),
    signal,
  });

  if (!res.ok) {
    throw new ChatbotStreamError(await parseErrorResponse(res), res.status);
  }

  const reader = res.body?.getReader();
  if (!reader) {
    throw new ChatbotStreamError('Resposta sem corpo');
  }

  const decoder = new TextDecoder();
  let carry = '';

  const handleEventBlock = (block: string) => {
    for (const line of block.split('\n')) {
      if (!line.startsWith('data:')) continue;
      const json = line.startsWith('data: ') ? line.slice(6) : line.slice(5).trimStart();
      if (!json) continue;
      let payload: SsePayload;
      try {
        payload = JSON.parse(json) as SsePayload;
      } catch {
        continue;
      }
      if (payload.type === 'token' && typeof payload.value === 'string') {
        onToken(payload.value);
      } else if (payload.type === 'error') {
        throw new ChatbotStreamError(
          typeof payload.message === 'string' ? payload.message : 'Erro no fluxo do assistente'
        );
      } else if (payload.type === 'cancel') {
        throw new ChatbotStreamError('Resposta cancelada');
      }
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      carry += decoder.decode(value, { stream: true });
      const chunks = carry.split('\n\n');
      carry = chunks.pop() ?? '';
      for (const block of chunks) {
        if (block.trim()) handleEventBlock(block);
      }
    }
    if (carry.trim()) handleEventBlock(carry);
  } finally {
    reader.releaseLock();
  }
}
