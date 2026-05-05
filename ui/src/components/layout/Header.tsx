import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Menu, User, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useGhostAuth } from '@/components/auth/ghost-auth/react/useGhostAuth';
import { useAccountModal } from '@/components/auth/useAccountModal';
import { useLoginModal } from '@/components/auth/useLoginModal';
import logoMamute from '@/assets/logo-mamute.png';

const navItems = [
  { path: '/', label: 'Início' },
  { path: '/selecao', label: 'Selecionar Parlamentares' },
  { path: '/dashboard', label: 'Dashboard Geral' },
  { path: '/pesquisa', label: 'Pesquisa IA' },
];

export function Header() {
  const location = useLocation();
  const token = useGhostAuth();
  const { openLogin } = useLoginModal();
  const { openAccount } = useAccountModal();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const visibleNavItems = token ? navItems : navItems//.filter((item) => item.path === '/');

  const handleAuthClick = () => {
    if (token) {
      closeMobileMenu();
      openAccount();
    } else {
      closeMobileMenu();
      openLogin();
    }
  };

  const closeMobileMenu = () => setIsMobileMenuOpen(false);
  const toggleMobileMenu = () => setIsMobileMenuOpen((current) => !current);

  useEffect(() => {
    closeMobileMenu();
  }, [location.pathname]);

  useEffect(() => {
    if (!isMobileMenuOpen) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isMobileMenuOpen]);

  // const handleAccountClick = () => {
  //   window.open(ACCOUNT_URL, '_blank', 'noopener,noreferrer');
  // };

  return (
    //TODO: Add sticky to the header
    <header className="top-0 z-50 w-full">
      <div
        className={cn(
          'fixed inset-0 z-40 bg-black/45 transition-opacity duration-200 md:hidden',
          isMobileMenuOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
        )}
        aria-hidden="true"
        onClick={closeMobileMenu}
      />
      <aside
        id="mobile-header-drawer"
        className={cn(
          'fixed top-0 left-0 z-50 h-full w-[86vw] max-w-[330px] border-r border-black/10 bg-white p-5 shadow-xl transition-transform duration-300 ease-out md:hidden',
          isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        )}
        aria-hidden={!isMobileMenuOpen}
      >
        <div className="mb-6 flex items-center justify-between">
          <Link to="/" className="flex items-center" onClick={closeMobileMenu}>
            <img src={logoMamute} alt="Mamute Político" className="h-[35px] w-auto" />
          </Link>
          <button
            type="button"
            onClick={closeMobileMenu}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full text-[#393939] transition hover:bg-black/5"
            aria-label="Fechar menu"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex flex-col gap-2">
          {visibleNavItems.map((item) => {
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                onClick={closeMobileMenu}
                className={cn(
                  'rounded-lg px-2 py-2 text-[16px] font-medium text-[#393939] transition-colors',
                  isActive ? 'bg-black/5' : 'hover:bg-black/5'
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <button
          type="button"
          onClick={handleAuthClick}
          className={cn(
            'mt-6 w-full cursor-pointer rounded-[92px] px-6 py-2 text-[11px] font-bold uppercase tracking-wide transition hover:opacity-90',
            'hover:bg-[#ff0004] hover:text-white bg-[#f5f5f5] text-black'
          )}
          aria-label={token ? 'Sair' : 'Iniciar Sessão'}
        >
          {token ? (
            <span className="flex items-center justify-center gap-2">
              <User className="h-5 w-5" />
              CONTA
            </span>
          ) : (
            'INICIAR SESSÃO'
          )}
        </button>
      </aside>
      <div className="container flex h-[88px] items-center justify-between">
        <div className="flex items-center gap-10">
          <Link to="/" className="flex items-center">
            <img src={logoMamute} alt="Mamute Político" className="h-[39px] w-auto" />
          </Link>

          <nav className="hidden md:flex items-center gap-3">
            {visibleNavItems.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={cn(
                    'px-1 py-1 text-[15px] font-medium text-[#393939] transition-opacity',
                    isActive ? 'underline underline-offset-4' : 'opacity-85 hover:opacity-100'
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={toggleMobileMenu}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full text-[#393939] transition hover:bg-black/5 md:hidden"
            aria-label={isMobileMenuOpen ? 'Fechar menu' : 'Abrir menu'}
            aria-expanded={isMobileMenuOpen}
            aria-controls="mobile-header-drawer"
          >
            {isMobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          {/* <button
            type="button"
            className="relative flex h-8 w-8 items-center justify-center rounded-full text-[#393939] transition hover:opacity-80"
            aria-label="Notificações"
          >
            <Bell className="h-[15px] w-[15px]" />
            <span className="absolute right-[4px] top-[1px] flex h-[15px] w-[15px] items-center justify-center rounded-full bg-black text-[10px] font-bold text-white">
              3
            </span>
          </button> */}
          {/* {token && (
            <button
              type="button"
              onClick={handleAuthClick}
              className="flex h-8 w-8 items-center justify-center rounded-full hover:bg-[#ff0004] hover:text-white border-[#393939] bg-white text-[#393939] transition hover:opacity-80"
              aria-label="Sua conta"
              title="Sua conta"
            >
              <User className="h-5 w-5" /> CONTA
            </button>
          )} */}
          {<button
            type="button"
            onClick={handleAuthClick}
            className={cn(
              'hidden cursor-pointer rounded-[92px] px-6 py-2 text-[11px] font-bold uppercase tracking-wide transition hover:opacity-90 md:inline-flex',
              'hover:bg-[#ff0004] hover:text-white bg-[#f5f5f5] text-black'
            )}
            aria-label={token ? 'Sair' : 'Iniciar Sessão'}
          >
            {token ? <div className="flex items-center gap-2"><User className="h-5 w-5" /><span className="hidden md:block">{" "}CONTA</span></div> : 'INICIAR SESSÃO'}
          </button>}
        </div>
      </div>
    </header>
  );
}
