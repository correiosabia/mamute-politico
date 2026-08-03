import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { MetricsLayout } from '@/components/admin/MetricsLayout';
import { useCredits, useIa } from '@/hooks/useMetrics';
import { CreditsPanel } from '@/components/admin/CreditsPanel';
import { brl, num } from '@/lib/adminFormat';

export default function AdminIaPage() {
  const { data, isLoading } = useIa();
  const credits = useCredits();

  return (
    <MetricsLayout title="IA" subtitle="Uso, custo e tokens do chatbot no mês corrente.">
      {credits.data && <CreditsPanel data={credits.data} />}

      {isLoading && (
        <div className="mp-card flex items-center gap-2 bg-white p-6 text-[#383838]/60">
          <Loader2 className="h-5 w-5 animate-spin" />
          Carregando…
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="mp-card bg-white p-5">
              <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">Consultas (mês)</p>
              <p className="mt-1 text-[26px] font-bold text-[#090909]">{num(data.consultas_mes)}</p>
            </div>
            <div className="mp-card bg-white p-5">
              <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">Custo (mês)</p>
              <p className="mt-1 text-[26px] font-bold text-[#090909]">{brl(data.custo_mes_brl)}</p>
            </div>
            <div className="mp-card bg-white p-5">
              <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">Tokens (mês)</p>
              <p className="mt-1 text-[26px] font-bold text-[#090909]">{num(data.tokens_mes)}</p>
            </div>
          </div>

          <div className="mp-card bg-white p-6">
            <h2 className="mb-1 text-[18px] font-bold text-[#090909]">Saúde do chatbot (mês)</h2>
            <p className="mb-4 text-[13px] text-[#383838]/50">
              Respostas vazias são consultas concluídas em que o usuário não recebeu nenhum texto.
            </p>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-6">
              <div>
                <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">Respostas OK</p>
                <p className="mt-1 text-[22px] font-bold text-[#090909]">{num(data.saude.respostas_ok)}</p>
              </div>
              <div>
                <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">Respostas vazias</p>
                <p className={`mt-1 text-[22px] font-bold ${data.saude.respostas_vazias > 0 ? 'text-[#d92d20]' : 'text-[#090909]'}`}>
                  {num(data.saude.respostas_vazias)}
                </p>
              </div>
              <div>
                <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">Falhas</p>
                <p className={`mt-1 text-[22px] font-bold ${data.saude.falhas > 0 ? 'text-[#d92d20]' : 'text-[#090909]'}`}>
                  {num(data.saude.falhas)}
                </p>
              </div>
              <div>
                <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">Canceladas</p>
                <p className="mt-1 text-[22px] font-bold text-[#090909]">{num(data.saude.canceladas)}</p>
              </div>
              <div>
                <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">Tempo médio</p>
                <p className="mt-1 text-[22px] font-bold text-[#090909]">
                  {data.saude.tempo_medio_s != null ? `${num(data.saude.tempo_medio_s)}s` : '—'}
                </p>
              </div>
              <div>
                <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">Tempo p95</p>
                <p className="mt-1 text-[22px] font-bold text-[#090909]">
                  {data.saude.tempo_p95_s != null ? `${num(data.saude.tempo_p95_s)}s` : '—'}
                </p>
              </div>
            </div>
          </div>

          <div className="mp-card bg-white p-6">
            <h2 className="mb-4 text-[18px] font-bold text-[#090909]">Consultas por dia</h2>
            {data.por_dia.length > 0 ? (
              <div className="h-[260px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.por_dia} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
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

          <div className="mp-card overflow-x-auto bg-white p-6">
            <h2 className="mb-4 text-[18px] font-bold text-[#090909]">Top usuários por custo</h2>
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr className="border-b border-[#383838]/10 text-[11px] uppercase tracking-wide text-[#383838]/50">
                  <th className="py-2 pr-3 font-semibold">Usuário</th>
                  <th className="py-2 pr-3 text-right font-semibold">Consultas</th>
                  <th className="py-2 pr-3 text-right font-semibold">Custo (R$)</th>
                </tr>
              </thead>
              <tbody>
                {data.top_usuarios.map((u) => (
                  <tr key={u.projeto_id} className="border-b border-[#383838]/5">
                    <td className="py-2 pr-3">
                      <Link
                        to={`/admin/metrics/users/${u.projeto_id}`}
                        className="font-medium text-[#1b76ff] no-underline hover:underline"
                      >
                        {u.nome || u.email}
                      </Link>
                    </td>
                    <td className="py-2 pr-3 text-right">{num(u.consultas_mes)}</td>
                    <td className="py-2 pr-3 text-right">{brl(u.custo_mes_brl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </MetricsLayout>
  );
}
