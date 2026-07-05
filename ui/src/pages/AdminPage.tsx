import { Link } from 'react-router-dom';
import { BarChart3, Database, Settings2, type LucideIcon } from 'lucide-react';
import { AdminShell } from '@/components/layout/AdminShell';

interface PanelCard {
  to: string;
  title: string;
  desc: string;
  icon: LucideIcon;
  available: boolean;
}

const PANELS: PanelCard[] = [
  {
    to: '/admin/tiers',
    title: 'Gestão de Tiers',
    desc: 'Edite os limites e o preço de cada plano. As mudanças valem na hora, sem redeploy.',
    icon: Settings2,
    available: true,
  },
  {
    to: '/admin/metrics',
    title: 'Métricas & Insights',
    desc: 'Uso de IA, custo e margem por usuário no mês corrente.',
    icon: BarChart3,
    available: true,
  },
  {
    to: '/admin/coverage',
    title: 'Cobertura do banco',
    desc: 'Quanto temos preenchido, por ano, casa e tipo (vs API aberta em breve).',
    icon: Database,
    available: true,
  },
];

export default function AdminPage() {
  return (
    <AdminShell footer="mammoth">
      <div>
        <h1 className="text-[36px] font-bold leading-none text-[#393939] md:text-[48px]">
          Painel administrativo
        </h1>
        <p className="mt-1 text-[18px] font-normal text-[#383838]">
          Configuração e insights do Mamute — acesso restrito a administradores
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {PANELS.map((panel) => (
          <div key={panel.title} className="mp-card flex flex-col gap-4 bg-white p-6">
            <div className="flex items-center gap-3">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[#1b76ff]/10 text-[#1b76ff]">
                <panel.icon className="h-6 w-6" />
              </span>
              <h2 className="text-[24px] font-bold leading-none text-[#090909]">
                {panel.title}
              </h2>
            </div>
            <p className="flex-1 text-[15px] leading-relaxed text-[#383838]">
              {panel.desc}
            </p>
            {panel.available ? (
              <Link
                to={panel.to}
                className="self-start rounded-full bg-[#1b76ff] px-5 py-2 text-[13px] font-semibold text-white no-underline transition-opacity hover:opacity-90"
              >
                Abrir painel
              </Link>
            ) : (
              <span className="self-start rounded-full border border-[#383838]/20 px-5 py-2 text-[13px] font-semibold text-[#383838]/50">
                Em breve
              </span>
            )}
          </div>
        ))}
      </div>
    </AdminShell>
  );
}
