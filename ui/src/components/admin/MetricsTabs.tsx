import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';

const TABS = [
  { to: '/admin/metrics', label: 'Geral', end: true },
  { to: '/admin/metrics/por-usuario', label: 'Por usuário' },
  { to: '/admin/metrics/ferramentas', label: 'Ferramentas' },
  { to: '/admin/metrics/parlamentares', label: 'Parlamentares' },
  { to: '/admin/metrics/ia', label: 'IA' },
];

export function MetricsTabs() {
  return (
    <nav className="flex flex-wrap gap-2">
      {TABS.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          className={({ isActive }) =>
            cn(
              'rounded-full px-4 py-1.5 text-[13px] font-semibold no-underline transition-colors',
              isActive
                ? 'bg-[#1b76ff] text-white'
                : 'bg-white/70 text-[#383838] hover:bg-white',
            )
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
