import { type ReactNode } from 'react';
import { Header } from '@/components/layout/Header';
import { SelecaoFooter } from '@/components/selecao/SelecaoFooter';
import banner3 from '@/assets/banner3-semfundo.png';
import logoMamute from '@/assets/logo-mamute.png';

type AdminFooter = 'mammoth' | 'green';

/**
 * Casca visual dos painéis admin: mesmo fundo dourado texturizado, header e
 * rodapé usados nas abas principais (Dashboard / Seleção).
 * - footer="mammoth": ilustração do Congresso (como na Dashboard).
 * - footer="green": barra verde enxuta (como na Seleção de Parlamentares).
 */
export function AdminShell({
  children,
  footer,
}: {
  children: ReactNode;
  footer?: AdminFooter;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-textura-gold">
      <Header />
      <main className="container flex-1 space-y-6 py-10">{children}</main>

      {footer === 'green' && <SelecaoFooter />}

      {footer === 'mammoth' && (
        <div className="relative mt-6 overflow-hidden">
          <img
            src={banner3}
            alt=""
            className="block h-auto w-full md:-mb-[250px]"
          />
          <div
            className="absolute bottom-5 left-4 right-4 flex flex-col items-start gap-2 sm:left-10 sm:right-10 sm:flex-row sm:items-center sm:justify-between"
            style={{ zIndex: 1 }}
          >
            <img
              src={logoMamute}
              alt="Mamute Político"
              style={{
                height: '47px',
                width: 'auto',
                filter: 'brightness(0) invert(1)',
              }}
            />
            <span
              className="mp-footer-note text-white"
              style={{ textShadow: '0 1px 2px rgba(0,0,0,0.5)' }}
            >
              2026 Mamute Político. Painel administrativo.
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
