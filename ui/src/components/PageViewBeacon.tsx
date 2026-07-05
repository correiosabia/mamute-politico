import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useGhostAuth } from '@/components/auth/ghost-auth/react/useGhostAuth';
import { sendPageView } from '@/api/events';

function pageLabel(pathname: string): string {
  if (pathname === '/' || pathname === '') return 'inicio';
  if (pathname.startsWith('/selecao')) return 'selecao';
  if (pathname.startsWith('/dashboard')) return 'dashboard';
  if (pathname.startsWith('/pesquisa')) return 'pesquisa';
  if (pathname.startsWith('/parlamentar')) return 'parlamentar';
  return pathname.replace(/^\//, '').split('/')[0] || 'inicio';
}

/** Registra page_view a cada troca de rota (exceto /admin) quando logado. */
export function PageViewBeacon() {
  const location = useLocation();
  const token = useGhostAuth();

  useEffect(() => {
    if (!token) return;
    if (location.pathname.startsWith('/admin')) return;
    sendPageView(pageLabel(location.pathname));
  }, [location.pathname, token]);

  return null;
}
