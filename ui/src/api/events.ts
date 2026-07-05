import { request } from './client';

function send(events: Array<Record<string, unknown>>): void {
  void request('/events', {
    method: 'POST',
    body: JSON.stringify({ events }),
  }).catch(() => {
    /* métrica é best-effort */
  });
}

/** Envia um page_view (fire-and-forget; nunca lança). */
export function sendPageView(page: string): void {
  send([{ type: 'page_view', page }]);
}

/** Envia um section_view (qual seção/aba o usuário viu dentro de uma tela). */
export function sendSectionView(page: string, section: string): void {
  send([{ type: 'section_view', page, section }]);
}
