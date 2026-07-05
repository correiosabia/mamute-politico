import { type ReactNode, useEffect, useRef } from 'react';
import { useGhostAuth } from '@/components/auth/ghost-auth/react/useGhostAuth';
import { sendSectionView } from '@/api/events';

/**
 * Envolve um bloco de tela e emite um `section_view` (uma vez) quando ele entra
 * na viewport. Best-effort: só dispara com usuário logado.
 */
export function TrackSection({
  page,
  section,
  className,
  children,
}: {
  page: string;
  section: string;
  className?: string;
  children: ReactNode;
}) {
  const token = useGhostAuth();
  const ref = useRef<HTMLDivElement>(null);
  const sent = useRef(false);

  useEffect(() => {
    if (!token || !ref.current || sent.current) return;
    const el = ref.current;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && !sent.current) {
            sent.current = true;
            sendSectionView(page, section);
            observer.disconnect();
          }
        }
      },
      { threshold: 0.4 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [token, page, section]);

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}
