import type { ReactNode } from 'react';
import { Lock } from 'lucide-react';

import { PLANS_URL } from '@/components/auth/config';

interface PaywallOverlayProps {
  /** Nome do recurso no texto do CTA, ex.: "a aba Emendas". */
  recurso: string;
  children: ReactNode;
}

/**
 * Vitrine do recurso pago (CS-58): o conteúdo real fica embaixo, desfocado e
 * inerte; por cima, a chamada para assinar. O desfoque é apresentação — o
 * dado que chega aqui já veio truncado do backend (`api/feature_gate.py`),
 * então inspecionar o DOM não revela nada além da prévia.
 */
export function PaywallOverlay({ recurso, children }: PaywallOverlayProps) {
  return (
    <div className="relative h-full overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none h-full select-none blur-[6px]"
      >
        {children}
      </div>
      <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-white/30 via-white/60 to-white/90">
        <div className="mx-6 flex max-w-md flex-col items-center gap-3 rounded-[20px] border border-black/10 bg-white p-6 text-center shadow-lg">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[#f5f5f5]">
            <Lock className="h-5 w-5 text-[#090909]" aria-hidden />
          </span>
          <p className="text-[15px] font-semibold text-[#090909]">
            Este conteúdo é exclusivo para assinantes
          </p>
          <p className="text-[13px] text-[#383838]/80">
            Assine um plano que inclui {recurso} para ver tudo — o que você vê
            atrás do desfoque é só uma amostra.
          </p>
          <a
            href={PLANS_URL}
            className="rounded-[76px] bg-[#1b76ff] px-6 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
          >
            ASSINAR PARA VER TUDO
          </a>
        </div>
      </div>
    </div>
  );
}
