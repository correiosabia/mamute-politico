import { Loader2 } from 'lucide-react';
import { MetricsLayout } from '@/components/admin/MetricsLayout';
import { useSections, useTools } from '@/hooks/useMetrics';
import { num } from '@/lib/adminFormat';

export default function AdminToolsPage() {
  const { data, isLoading } = useTools();
  const sectionsQuery = useSections();
  const sections = sectionsQuery.data?.sections ?? [];
  const tools = data?.tools ?? [];
  const max = Math.max(1, ...tools.map((t) => t.uses));

  return (
    <MetricsLayout title="Ferramentas" subtitle="Uso das principais ferramentas do sistema.">
      {isLoading ? (
        <div className="mp-card flex items-center gap-2 bg-white p-6 text-[#383838]/60">
          <Loader2 className="h-5 w-5 animate-spin" />
          Carregando…
        </div>
      ) : tools.length > 0 ? (
        <div className="mp-card space-y-4 bg-white p-6">
          {tools.map((t) => (
            <div key={t.tool}>
              <div className="flex items-center justify-between text-[14px]">
                <span className="text-[#383838]">{t.tool}</span>
                <span className="font-semibold text-[#090909]">{num(t.uses)}</span>
              </div>
              <div className="mt-1.5 h-2 w-full rounded-full bg-[#eee]">
                <div
                  className="h-2 rounded-full bg-[#1b76ff]"
                  style={{ width: `${(t.uses / max) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mp-card bg-white p-6 text-[#383838]/60">
          Sem uso registrado ainda. A navegação começa a contar quando os usuários
          usam o app (o beacon de páginas coleta a partir do deploy).
        </div>
      )}

      <div className="mp-card bg-white p-6">
        <h2 className="mb-1 text-[18px] font-bold text-[#090909]">Seções mais vistas</h2>
        <p className="mb-4 text-[12px] text-[#383838]/50">
          O que os usuários mais abrem dentro de cada tela (ex.: abas da página de parlamentar).
        </p>
        {sections.length > 0 ? (
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-[#383838]/10 text-[11px] uppercase tracking-wide text-[#383838]/50">
                <th className="py-2 pr-3 font-semibold">Tela</th>
                <th className="py-2 pr-3 font-semibold">Seção</th>
                <th className="py-2 pr-3 text-right font-semibold">Visualizações</th>
              </tr>
            </thead>
            <tbody>
              {sections.map((s) => (
                <tr key={`${s.page}-${s.section}`} className="border-b border-[#383838]/5">
                  <td className="py-2 pr-3 text-[#383838]">{s.page}</td>
                  <td className="py-2 pr-3 font-medium capitalize text-[#090909]">
                    {s.section.replace(/-/g, ' ')}
                  </td>
                  <td className="py-2 pr-3 text-right font-semibold">{num(s.views)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-[14px] text-[#383838]/50">
            Sem dados de seção ainda (coleta a partir do deploy do front instrumentado).
          </p>
        )}
      </div>
    </MetricsLayout>
  );
}
