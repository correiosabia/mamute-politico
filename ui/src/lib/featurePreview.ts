/**
 * Preview de admin: "ver como bloqueada" (CS-58).
 *
 * Lente de inspeção, não config do produto: vive no localStorage DESTE
 * navegador e não vai ao banco. Com o preview ligado para uma chave, a UI
 * renderiza a feature como bloqueada (cadeado + blur + CTA) e as chamadas de
 * dado saem com `X-Feature-Preview`, que o backend só honra para admin
 * (`api/feature_gate.py`) — a truncagem real entra na simulação. Usuário
 * comum que forjar isto só borra a própria tela: o header é ignorado no
 * servidor.
 */

const STORAGE_KEY = 'mp-feature-preview';
const EVENTO = 'mp-feature-preview-change';

// Cache para o snapshot ser referência-estável enquanto o storage não muda —
// exigência do useSyncExternalStore (snapshot novo a cada chamada = loop).
let cacheRaw: string | null = null;
let cacheKeys: string[] = [];

export function getPreviewKeys(): string[] {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch {
    return cacheKeys;
  }
  if (raw === cacheRaw) return cacheKeys;
  let keys: string[] = [];
  try {
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    keys = Array.isArray(parsed)
      ? parsed.filter((k): k is string => typeof k === 'string')
      : [];
  } catch {
    keys = [];
  }
  cacheRaw = raw;
  cacheKeys = keys;
  return cacheKeys;
}

export function isFeaturePreviewOn(key: string): boolean {
  return getPreviewKeys().includes(key);
}

export function toggleFeaturePreview(key: string): void {
  const atual = getPreviewKeys();
  const proximo = atual.includes(key)
    ? atual.filter((k) => k !== key)
    : [...atual, key];
  localStorage.setItem(STORAGE_KEY, JSON.stringify(proximo));
  window.dispatchEvent(new Event(EVENTO));
}

export function subscribeFeaturePreview(cb: () => void): () => void {
  window.addEventListener(EVENTO, cb);
  // 'storage' cobre outra aba do mesmo navegador mexendo no toggle.
  window.addEventListener('storage', cb);
  return () => {
    window.removeEventListener(EVENTO, cb);
    window.removeEventListener('storage', cb);
  };
}

/** Valor do header `X-Feature-Preview`, ou null sem preview ativo. */
export function previewHeaderValue(): string | null {
  const keys = getPreviewKeys();
  return keys.length > 0 ? keys.join(',') : null;
}
