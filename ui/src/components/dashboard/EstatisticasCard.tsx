import type { DashboardStatsOut } from '@/api/types';

interface EstatisticasCardProps {
  stats?: DashboardStatsOut;
  isLoading?: boolean;
}

export function EstatisticasCard({ stats, isLoading = false }: EstatisticasCardProps) {
  const statsItems = [
    {
      value: !isLoading && stats != null ? String(stats.propositions_this_week) : '--',
      label: 'Projetos\n3 meses',
    },
    {
      value:
        !isLoading && stats?.attendance_avg_percent != null
          ? `${stats.attendance_avg_percent}%`
          : '--',
      label: 'Presença\nmédia',
    },
    {
      value: !isLoading && stats != null ? String(stats.recent_votes_count) : '--',
      label: 'Votações\nrecentes',
    },
    {
      value: !isLoading && stats != null ? String(stats.speeches_count) : '--',
      label: 'Discursos',
    },
  ];

  return (
    <div className="mp-card bg-white p-6">
      <h2 className="mb-4 text-[32px] leading-none font-bold text-[#090909]">Estatísticas</h2>
      <div className="flex items-start justify-between gap-2">
        {statsItems.map((stat) => (
          <div key={stat.label} className="flex flex-col items-center gap-2">
            <div className="w-[49px] h-[49px] flex items-center justify-center rounded-full border border-[#878787]">
              <p className="text-[18px] font-bold text-[#468fff]">{stat.value}</p>
            </div>
            <p className="text-[13px] text-[#383838] text-center leading-tight whitespace-pre-line">
              {stat.label}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
