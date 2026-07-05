import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { AdminShell } from '@/components/layout/AdminShell';
import { fetchCoverage } from '@/api/admin';
import { num } from '@/lib/adminFormat';

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="mp-card bg-white p-5">
      <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">{label}</p>
      <p className="mt-1 text-[26px] font-bold leading-none text-[#090909]">{value}</p>
    </div>
  );
}

export default function AdminCoveragePage() {
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'coverage'],
    queryFn: fetchCoverage,
  });

  return (
    <AdminShell footer="green">
      <Link
        to="/admin"
        className="inline-flex w-fit items-center gap-1.5 rounded-full border border-[#383838]/20 px-3 py-1 text-[12px] font-semibold text-[#383838] no-underline transition-colors hover:bg-[#383838]/10"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Painel administrativo
      </Link>
      <div>
        <h1 className="text-[36px] font-bold leading-none text-[#393939] md:text-[48px]">
          Cobertura do banco
        </h1>
        <p className="mt-1 text-[18px] font-normal text-[#383838]">
          Quanto temos preenchido, por ano, casa e tipo.
        </p>
      </div>

      {isLoading && (
        <div className="mp-card flex items-center gap-2 bg-white p-6 text-[#383838]/60">
          <Loader2 className="h-5 w-5 animate-spin" />
          Carregando…
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
            <Kpi label="Proposições" value={num(data.totals.proposicoes)} />
            <Kpi label="Votações" value={num(data.totals.votacoes)} />
            <Kpi label="Discursos" value={num(data.totals.discursos)} />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="mp-card overflow-x-auto bg-white p-6">
              <h2 className="mb-4 text-[18px] font-bold text-[#090909]">Proposições por ano e casa</h2>
              <table className="w-full text-left text-[13px]">
                <thead>
                  <tr className="border-b border-[#383838]/10 text-[11px] uppercase tracking-wide text-[#383838]/50">
                    <th className="py-2 pr-3 font-semibold">Ano</th>
                    <th className="py-2 pr-3 text-right font-semibold">Câmara</th>
                    <th className="py-2 pr-3 text-right font-semibold">Senado</th>
                    <th className="py-2 pr-3 text-right font-semibold">Total</th>
                    <th className="py-2 pr-3 text-right font-semibold">API Câmara</th>
                    <th className="py-2 pr-3 text-right font-semibold">% Câmara</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_year_house.map((r) => (
                    <tr key={String(r.year)} className="border-b border-[#383838]/5">
                      <td className="py-2 pr-3 font-medium text-[#090909]">{r.year ?? '—'}</td>
                      <td className="py-2 pr-3 text-right">{num(r.camara)}</td>
                      <td className="py-2 pr-3 text-right">{num(r.senado)}</td>
                      <td className="py-2 pr-3 text-right font-semibold">{num(r.total)}</td>
                      <td className="py-2 pr-3 text-right text-[#383838]/60">
                        {r.api_camara != null ? num(r.api_camara) : '—'}
                      </td>
                      <td className="py-2 pr-3 text-right font-semibold text-[#090909]">
                        {r.cobertura_camara_pct != null ? `${r.cobertura_camara_pct}%` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mp-card bg-white p-6">
              <h2 className="mb-4 text-[18px] font-bold text-[#090909]">Proposições por tipo</h2>
              <ul className="space-y-2">
                {data.by_type.slice(0, 12).map((t) => (
                  <li key={t.type} className="flex items-center justify-between text-[14px]">
                    <span className="text-[#383838]">{t.type}</span>
                    <span className="font-semibold text-[#090909]">{num(t.count)}</span>
                  </li>
                ))}
                {data.by_type.length === 0 && (
                  <li className="text-[13px] text-[#383838]/50">Sem proposições no banco.</li>
                )}
              </ul>
            </div>
          </div>

          <div className="mp-card bg-white p-4 text-[12px] text-[#383838]/50">
            "% Câmara" = nossas proposições da Câmara ÷ total da API aberta da Câmara
            no ano (via job de sync). Senado é a próxima etapa. A casa é derivada da
            casa do autor da proposição.
          </div>
        </>
      )}
    </AdminShell>
  );
}
