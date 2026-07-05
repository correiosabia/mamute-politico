import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Loader2 } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AdminShell } from '@/components/layout/AdminShell';
import { useUserDetail } from '@/hooks/useMetrics';

const brl = (v: number) =>
  v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const num = (v: number) => v.toLocaleString('pt-BR');

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="mp-card bg-white p-5">
      <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">
        {label}
      </p>
      <p className="mt-1 text-[26px] font-bold leading-none text-[#090909]">{value}</p>
    </div>
  );
}

export default function AdminUserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: u, isLoading, error } = useUserDetail(Number(id));

  return (
    <AdminShell footer="green">
      <Link
        to="/admin/metrics"
        className="inline-flex w-fit items-center gap-1.5 rounded-full border border-[#383838]/20 px-3 py-1 text-[12px] font-semibold text-[#383838] no-underline transition-colors hover:bg-[#383838]/10"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Métricas
      </Link>

      {isLoading && (
        <div className="mp-card flex items-center gap-2 bg-white p-6 text-[#383838]/60">
          <Loader2 className="h-5 w-5 animate-spin" />
          Carregando usuário…
        </div>
      )}
      {error && (
        <div className="mp-card bg-white p-6 text-destructive">
          Usuário não encontrado.
        </div>
      )}

      {u && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-[32px] font-bold leading-none text-[#393939] md:text-[40px]">
                {u.nome || u.email}
              </h1>
              <p className="mt-1 text-[15px] text-[#383838]">{u.email}</p>
            </div>
            <span className="rounded-full bg-[#1b76ff]/10 px-3 py-1 text-[12px] font-bold text-[#1b76ff]">
              {u.plano ?? 'sem plano'}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Kpi
              label="Consultas IA (mês)"
              value={`${num(u.consultas_mes)}${u.limite_consultas != null ? ` / ${u.limite_consultas}` : ''}`}
            />
            <Kpi label="Custo IA (mês)" value={brl(u.custo_mes_brl)} />
            <Kpi label="Margem (mês)" value={brl(u.margem_mes)} />
            <Kpi
              label="Parlamentares"
              value={`${num(u.parlamentares_monitorados)}${u.limite_parlamentares != null ? ` / ${u.limite_parlamentares}` : ''}`}
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="mp-card bg-white p-6">
              <h2 className="mb-4 text-[18px] font-bold text-[#090909]">
                Consultas de IA por dia
              </h2>
              {u.ia_por_dia.length > 0 ? (
                <div className="h-[240px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={u.ia_por_dia} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                      <XAxis dataKey="dia" tick={{ fontSize: 10 }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Bar dataKey="consultas" fill="#1b76ff" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="text-[14px] text-[#383838]/50">Sem consultas registradas.</p>
              )}
            </div>

            <div className="mp-card bg-white p-6">
              <h2 className="mb-4 text-[18px] font-bold text-[#090909]">
                Páginas mais usadas
              </h2>
              {u.paginas.length > 0 ? (
                <ul className="space-y-2">
                  {u.paginas.map((p) => (
                    <li key={p.page} className="flex items-center justify-between text-[14px]">
                      <span className="capitalize text-[#383838]">{p.page}</span>
                      <span className="font-semibold text-[#090909]">{num(p.views)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[14px] text-[#383838]/50">
                  Sem navegação registrada ainda (o beacon começa a coletar a partir de agora).
                </p>
              )}
              <div className="mt-5 border-t border-[#383838]/10 pt-4">
                <h3 className="text-[12px] font-bold uppercase tracking-wide text-[#383838]/50">
                  Trocas de parlamentares
                </h3>
                <p className="mt-1 text-[14px] text-[#383838]">
                  {num(u.trocas.adicionados)} adicionados · {num(u.trocas.removidos)} removidos
                  <span className="text-[#383838]/50"> ({num(u.trocas.total)} no total)</span>
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </AdminShell>
  );
}
