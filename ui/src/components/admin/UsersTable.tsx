import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import type { MetricsUser } from '@/api/admin';
import { brl, num } from '@/lib/adminFormat';

export function UsersTable({ users, rate }: { users: MetricsUser[]; rate?: number }) {
  return (
    <div className="mp-card overflow-x-auto bg-white p-6">
      <table className="w-full min-w-[760px] text-left text-[13px]">
        <thead>
          <tr className="border-b border-[#383838]/10 text-[11px] uppercase tracking-wide text-[#383838]/50">
            <th className="py-2 pr-3 font-semibold">Usuário</th>
            <th className="py-2 pr-3 font-semibold">Plano</th>
            <th className="py-2 pr-3 text-right font-semibold">Consultas</th>
            <th className="py-2 pr-3 text-right font-semibold">Tokens</th>
            <th className="py-2 pr-3 text-right font-semibold">Custo (R$)</th>
            <th className="py-2 pr-3 text-right font-semibold">Preço (R$)</th>
            <th className="py-2 pr-3 text-right font-semibold">Margem (R$)</th>
            <th className="py-2 pr-3 text-right font-semibold">Parlam.</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.projeto_id} className="border-b border-[#383838]/5 transition-colors hover:bg-[#f8f8f8]">
              <td className="py-2 pr-3">
                <Link
                  to={`/admin/metrics/users/${u.projeto_id}`}
                  className="inline-flex items-center gap-1 font-medium text-[#1b76ff] no-underline hover:underline"
                  title={u.email}
                >
                  {u.nome || u.email}
                  <ChevronRight className="h-3.5 w-3.5" />
                </Link>
                {u.acima_do_plano && (
                  <span className="ml-2 rounded-full bg-[#ff0004]/10 px-2 py-0.5 text-[10px] font-bold text-[#ff0004]">
                    acima do plano
                  </span>
                )}
              </td>
              <td className="py-2 pr-3 text-[#383838]">{u.plano ?? '—'}</td>
              <td className="py-2 pr-3 text-right">
                {num(u.consultas_mes)}
                {u.limite_consultas != null && (
                  <span className="text-[#383838]/40">/{u.limite_consultas}</span>
                )}
              </td>
              <td className="py-2 pr-3 text-right">{num(u.tokens_mes)}</td>
              <td className="py-2 pr-3 text-right">{brl(u.custo_mes_brl)}</td>
              <td className="py-2 pr-3 text-right">{brl(u.preco_mensal)}</td>
              <td className="py-2 pr-3 text-right font-medium text-[#090909]">{brl(u.margem_mes)}</td>
              <td className="py-2 pr-3 text-right">
                {num(u.parlamentares_monitorados)}
                {u.limite_parlamentares != null && (
                  <span className="text-[#383838]/40">/{u.limite_parlamentares}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rate != null && (
        <p className="mt-3 text-[11px] text-[#383838]/50">
          Custo e margem em R$ (custo dos modelos convertido de US$). Câmbio: US$ 1 = {brl(rate)}.
        </p>
      )}
    </div>
  );
}
