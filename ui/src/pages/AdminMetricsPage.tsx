import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { MetricsLayout } from '@/components/admin/MetricsLayout';
import { UsersTable } from '@/components/admin/UsersTable';
import {
  useMetricsOverview,
  useMetricsUsers,
  useParliamentarians,
  useTools,
} from '@/hooks/useMetrics';
import { brl, num } from '@/lib/adminFormat';

function Kpi({ label, value, tone }: { label: string; value: string; tone?: 'warn' }) {
  return (
    <div className="mp-card bg-white p-5">
      <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">{label}</p>
      <p className={`mt-1 text-[26px] font-bold leading-none ${tone === 'warn' ? 'text-[#ff0004]' : 'text-[#090909]'}`}>
        {value}
      </p>
    </div>
  );
}

export default function AdminMetricsPage() {
  const overview = useMetricsOverview();
  const usersQuery = useMetricsUsers({ limit: 20 });
  const tools = useTools();
  const parl = useParliamentarians();
  const users = usersQuery.data?.users ?? [];

  return (
    <MetricsLayout
      title="Métricas & Insights"
      subtitle="Visão geral do uso do sistema no mês corrente."
    >
      {overview.isLoading && (
        <div className="mp-card flex items-center gap-2 bg-white p-6 text-[#383838]/60">
          <Loader2 className="h-5 w-5 animate-spin" />
          Carregando métricas…
        </div>
      )}

      {overview.data && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Kpi label="Usuários" value={num(overview.data.usuarios)} />
          <Kpi label="Consultas IA (mês)" value={num(overview.data.consultas_mes)} />
          <Kpi label="Receita (mês)" value={brl(overview.data.receita_mes)} />
          <Kpi label="Margem (mês)" value={brl(overview.data.margem_mes)} />
          <Kpi label="Custo IA (mês)" value={brl(overview.data.custo_mes_brl)} />
          <Kpi label="Parlamentares monitorados" value={num(overview.data.parlamentares_monitorados)} />
          <Kpi label="Tokens (mês)" value={num(overview.data.tokens_mes)} />
          <Kpi
            label="Acima do plano"
            value={num(overview.data.usuarios_acima_do_plano)}
            tone={overview.data.usuarios_acima_do_plano > 0 ? 'warn' : undefined}
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Ferramentas mais usadas (resumo) */}
        <div className="mp-card bg-white p-6">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[18px] font-bold text-[#090909]">Ferramentas mais usadas</h2>
            <Link to="/admin/metrics/ferramentas" className="text-[12px] font-semibold text-[#1b76ff] no-underline hover:underline">
              ver tudo
            </Link>
          </div>
          <ul className="space-y-2">
            {(tools.data?.tools ?? []).slice(0, 5).map((t) => (
              <li key={t.tool} className="flex items-center justify-between text-[14px]">
                <span className="text-[#383838]">{t.tool}</span>
                <span className="font-semibold text-[#090909]">{num(t.uses)}</span>
              </li>
            ))}
            {tools.data && tools.data.tools.length === 0 && (
              <li className="text-[13px] text-[#383838]/50">Sem uso registrado ainda.</li>
            )}
          </ul>
        </div>

        {/* Parlamentares mais monitorados (resumo) */}
        <div className="mp-card bg-white p-6">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[18px] font-bold text-[#090909]">Parlamentares monitorados</h2>
            <Link to="/admin/metrics/parlamentares" className="text-[12px] font-semibold text-[#1b76ff] no-underline hover:underline">
              ver tudo
            </Link>
          </div>
          {parl.data && (
            <>
              <div className="mb-3 flex gap-2 text-[12px]">
                <span className="rounded-full bg-[#1b76ff]/10 px-3 py-1 font-bold text-[#1b76ff]">
                  Câmara {num(parl.data.by_house.camara)}
                </span>
                <span className="rounded-full bg-[#09a03b]/10 px-3 py-1 font-bold text-[#09a03b]">
                  Senado {num(parl.data.by_house.senado)}
                </span>
              </div>
              <ul className="space-y-2">
                {parl.data.top.slice(0, 5).map((p) => (
                  <li key={p.parliamentarian_id} className="flex items-center justify-between text-[14px]">
                    <span className="text-[#383838]">
                      {p.name || `#${p.parliamentarian_id}`}
                      <span className="text-[#383838]/40"> · {p.state || '—'}</span>
                    </span>
                    <span className="font-semibold text-[#090909]">{num(p.monitors)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between">
        <h2 className="text-[20px] font-bold text-[#090909]">Top 20 usuários por custo</h2>
        <Link to="/admin/metrics/por-usuario" className="text-[13px] font-semibold text-[#1b76ff] no-underline hover:underline">
          ver todos / filtrar →
        </Link>
      </div>
      {users.length > 0 ? (
        <UsersTable users={users} rate={usersQuery.data?.usd_brl_rate} />
      ) : (
        <div className="mp-card bg-white p-6 text-[#383838]/60">
          Sem dados de uso ainda (o registro depende da quota estar ligada).
        </div>
      )}
    </MetricsLayout>
  );
}
