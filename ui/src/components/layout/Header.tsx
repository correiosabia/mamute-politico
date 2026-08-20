import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronDown, Menu, User, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useGhostAuth } from '@/components/auth/ghost-auth/react/useGhostAuth';
import { useIsAdmin } from '@/hooks/useIsAdmin';
import { useAccountModal } from '@/components/auth/useAccountModal';
import { useLoginModal } from '@/components/auth/useLoginModal';
import logoMamute from '@/assets/logo-mamute.png';

const siteRootUrl = '/#/';
const parceriasUrl = 'https://mamutepolitico.com.br/seja-parceiro/';

type NavLeaf =
  | { id: string; label: string; path: string }
  | { id: string; label: string; href: string; external: true; newTab?: boolean };

type NavGroup = { id: string; label: string; children: NavLeaf[] };

type NavItem = NavLeaf | NavGroup;

const isGroup = (item: NavItem): item is NavGroup => 'children' in item;

const navItems: NavItem[] = [
  { id: 'home', path: '/', label: 'Início' },
  { id: 'selecao', path: '/selecao', label: 'Selecionar Parlamentares' },
  { id: 'dashboard', path: '/dashboard', label: 'Dashboard Geral' },
  { id: 'pesquisa', path: '/pesquisa', label: 'Pesquisa IA' },
  {
    id: 'contato',
    label: 'Contato',
    children: [
      { id: 'parcerias', href: parceriasUrl, label: 'Parcerias', external: true, newTab: true },
      { id: 'blog', href: siteRootUrl, label: 'Blog', external: true },
    ],
  },
];

function NavLeafLink({
  item,
  className,
  onNavigate,
}: {
  item: NavLeaf;
  className: string;
  onNavigate?: () => void;
}) {
  if ('external' in item) {
    return (
      <a
        href={item.href}
        onClick={onNavigate}
        className={className}
        {...(item.newTab ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
      >
        {item.label}
      </a>
    );
  }

  return (
    <Link to={item.path} onClick={onNavigate} className={className}>
      {item.label}
    </Link>
  );
}

export function Header() {
  const location = useLocation();
  const token = useGhostAuth();
  const { isAdmin } = useIsAdmin();
  const { openLogin } = useLoginModal();
  const { openAccount } = useAccountModal();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [openSubmenuId, setOpenSubmenuId] = useState<string | null>(null);
  const baseNavItems = token ? navItems : navItems;//.filter((item) => item.path === '/');
  const visibleNavItems: NavItem[] = isAdmin
    ? [...baseNavItems, { id: 'admin', path: '/admin', label: 'Admin' }]
    : baseNavItems;

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
    setOpenSubmenuId(null);
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

  const isActivePath = (item: NavLeaf) => !('external' in item) && location.pathname === item.path;

  const desktopLinkClass = (item: NavLeaf) =>
    cn(
      'px-1 py-1 text-[15px] font-medium text-[#393939] transition-opacity',
      isActivePath(item) ? 'underline underline-offset-4' : 'opacity-85 hover:opacity-100'
    );

  const mobileLinkClass = (item: NavLeaf) =>
    cn(
      'rounded-lg px-2 py-2 text-[16px] font-medium text-[#393939] transition-colors',
      isActivePath(item) ? 'bg-black/5' : 'hover:bg-black/5'
    );

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
          {visibleNavItems.map((item) =>
            isGroup(item) ? (
              <div key={item.id} className="flex flex-col gap-1">
                <span className="px-2 py-2 text-[16px] font-medium text-[#393939]">
                  {item.label}
                </span>
                {item.children.map((child) => (
                  <NavLeafLink
                    key={child.id}
                    item={child}
                    className={cn(mobileLinkClass(child), 'ml-3 text-[15px]')}
                    onNavigate={closeMobileMenu}
                  />
                ))}
              </div>
            ) : (
              <NavLeafLink
                key={item.id}
                item={item}
                className={mobileLinkClass(item)}
                onNavigate={closeMobileMenu}
              />
            )
          )}
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
              if (!isGroup(item)) {
                return <NavLeafLink key={item.id} item={item} className={desktopLinkClass(item)} />;
              }

              const isSubmenuOpen = openSubmenuId === item.id;

              return (
                <div
                  key={item.id}
                  className="relative"
                  onMouseEnter={() => setOpenSubmenuId(item.id)}
                  onMouseLeave={() => setOpenSubmenuId(null)}
                  onFocus={() => setOpenSubmenuId(item.id)}
                  onBlur={(event) => {
                    // Fecha só quando o foco sai do conjunto gatilho + painel.
                    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                      setOpenSubmenuId(null);
                    }
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') {
                      setOpenSubmenuId(null);
                    }
                  }}
                >
                  <button
                    type="button"
                    onClick={() => setOpenSubmenuId(isSubmenuOpen ? null : item.id)}
                    className={cn(
                      'flex items-center gap-1 px-1 py-1 text-[15px] font-medium text-[#393939] transition-opacity',
                      isSubmenuOpen ? 'opacity-100' : 'opacity-85 hover:opacity-100'
                    )}
                    aria-expanded={isSubmenuOpen}
                    aria-controls={`nav-submenu-${item.id}`}
                    aria-haspopup="true"
                  >
                    {item.label}
                    <ChevronDown
                      className={cn('h-4 w-4 transition-transform', isSubmenuOpen && 'rotate-180')}
                      aria-hidden="true"
                    />
                  </button>

                  {isSubmenuOpen && (
                    <div
                      id={`nav-submenu-${item.id}`}
                      className="absolute left-1/2 top-full z-50 min-w-[168px] -ml-2.5 -translate-x-1/2 pt-3"
                    >
                          <div className="flex flex-col rounded-2xl border border-black/10 bg-[#e6c54a]/80 p-2 shadow-[0_8px_18px_rgba(0,0,0,0.14)] backdrop-blur-md">
                            {item.children.map((child) => (
                              <NavLeafLink
                                key={child.id}
                                item={child}
                                className={cn(
                                  'rounded-lg px-3 py-2 text-center text-[15px] font-medium text-[#393939] transition-colors hover:bg-black/10',
                                  isActivePath(child) && 'bg-black/10'
                                )}
                                onNavigate={() => setOpenSubmenuId(null)}
                              />
                            ))}
                      </div>
                    </div>
                  )}
                </div>
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
