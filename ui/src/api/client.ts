const getBaseUrl = (): string => {
  const root = import.meta.env.VITE_BASE_URL;
  if (root && typeof root === 'string') {
    return `${root.replace(/\/$/, '')}/api`;
  }
  // Same-origin: Caddy (prod/dev) faz proxy /api -> api:8000.
  // Em `npm run dev` standalone, vite.config server.proxy cobre o mesmo path.
  return '/api';
};

import { JWT_TOKEN_KEY } from '@/components/auth/config';

/** Ghost Members JWT: from localStorage (same key as auth flow) then env fallback. Used for all API requests. */
const getToken = (): string | undefined => {

  if (typeof window !== 'undefined') {
    const stored = localStorage.getItem(JWT_TOKEN_KEY);
    if (stored) return stored;
  }
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function request<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const baseUrl = getBaseUrl();
  const token = getToken();
  const url = path.startsWith('http') ? path : `${baseUrl}${path.startsWith('/') ? path : `/${path}`}`;

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(init?.headers ?? {}),
  };
  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(url, {
    ...init,
    method: init?.method ?? 'GET',
    headers,
  });

  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = body.detail ?? (typeof body.detail === 'string' ? body.detail : undefined);
    } catch {
      detail = await res.text() || undefined;
    }
    const message =
      res.status === 401
        ? 'Token ausente ou expirado. Faça login para continuar.'
        : res.status === 404
          ? 'Recurso não encontrado.'
          : detail || res.statusText || `Erro ${res.status}`;
    throw new ApiError(message, res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
