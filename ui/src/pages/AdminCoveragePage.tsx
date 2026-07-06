import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { AdminShell } from '@/components/layout/AdminShell';
import { fetchCoverage } from '@/api/admin';
import type { Coverage, CoverageStatus } from '@/api/admin';
import { num } from '@/lib/adminFormat';

const STATUS_META: Record<CoverageStatus, { label: string; cls: string }> = {
  completo: { label: 'Completo', cls: 'bg-emerald-100 text-emerald-700' },
  quase: { label: 'Quase', cls: 'bg-amber-100 text-amber-700' },
  parcial: { label: 'Parcial', cls: 'bg-red-100 text-red-700' },
  superset: { label: 'Superset*', cls: 'bg-indigo-100 text-indigo-700' },
  sem_referencia: { label: 'Sem ref.', cls: 'bg-slate-200 text-slate-600' },
  ausente: { label: 'Ausente', cls: 'bg-slate-300 text-slate-700' },
};

function Badge({ status }: { status: CoverageStatus }) {
  const m = STATUS_META[status] ?? STATUS_META.sem_referencia;
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${m.cls}`}>
      {m.label}
    </span>
  );
}

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

function Section({
  n,
  title,
  children,
  nota,
}: {
  n: number;
  title: string;
  children: React.ReactNode;
  nota?: string;
}) {
  return (
    <div className="space-y-3">
      <h2 className="text-[20px] font-bold text-[#090909]">
        {n}. {title}
      </h2>
      {children}
      {nota && (
        <p className="rounded-xl bg-[#383838]/[0.04] p-3 text-[12px] leading-relaxed text-[#383838]/70">
          {nota}
        </p>
      )}
    </div>
  );
}

/** Tabela com anos nas COLUNAS (Câmara/Senado nas linhas) — igual ao relatório. */
function YearMatrix({
  rows,
}: {
  rows: { label: string; data: { year: number; nosso: number }[] }[];
}) {
  const years = Array.from(
    new Set(rows.flatMap((r) => r.data.map((d) => d.year))),
  ).sort((a, b) => a - b);
  const lookup = (data: { year: number; nosso: number }[], y: number) =>
    data.find((d) => d.year === y)?.nosso ?? 0;
  return (
    <div className="mp-card overflow-x-auto bg-white p-5">
      <table className="w-full text-right text-[13px]">
        <thead>
          <tr className="border-b border-[#383838]/10 text-[#383838]/50">
            <th className="py-2 pr-3 text-left font-semibold">Casa</th>
            {years.map((y) => (
              <th key={y} className="px-2 py-2 font-semibold">
                {y}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-b border-[#383838]/5">
              <td className="py-2 pr-3 text-left font-semibold text-[#090909]">
                {r.label}
              </td>
              {years.map((y) => (
                <td key={y} className="px-2 py-2 tabular-nums">
                  {num(lookup(r.data, y))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
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
          Cobertura da base de dados
        </h1>
        <p className="mt-1 text-[18px] font-normal text-[#383838]">
          Comparativo com as APIs oficiais de dados abertos (Câmara e Senado).
        </p>
        {data?.computed_at && (
          <p className="mt-1 text-[13px] text-[#383838]/60">
            Atualizado em{' '}
            {new Date(data.computed_at).toLocaleString('pt-BR', {
              dateStyle: 'short',
              timeStyle: 'short',
            })}{' '}
            · recalculado 1x/dia
          </p>
        )}
      </div>

      {isLoading && (
        <div className="mp-card flex items-center gap-2 bg-white p-6 text-[#383838]/60">
          <Loader2 className="h-5 w-5 animate-spin" />
          Carregando…
        </div>
      )}

      {data?.pending && (
        <div className="mp-card bg-amber-50 p-6 text-[14px] text-amber-800">
          A cobertura ainda não foi computada. Ela é gerada pela rotina diária das 04h
          (ou rode <code>python -m mamute_scrappers.scripts.refresh_admin_caches</code>).
        </div>
      )}

      {data && !data.pending && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Kpi label="Proposições" value={num(data.kpis.proposicoes)} />
            <Kpi label="Discursos" value={num(data.kpis.discursos)} />
            <Kpi label="Votações nominais" value={num(data.kpis.votacoes_nominais)} />
            <Kpi label="Parlamentares" value={num(data.kpis.parlamentares)} />
          </div>

          {/* Metodologia + legenda */}
          <div className="mp-card space-y-2 bg-white p-5 text-[12px] leading-relaxed text-[#383838]/70">
            <p>
              <b>Metodologia:</b> "Nosso" = contagem na base do Mamute; "Oficial" = total
              retornado pela API oficial para o mesmo ano. A casa é derivada do autor
              (Câmara = proposições cujo autor não é senador). O % aparece só onde a
              comparação é justa — em votações a base guarda apenas as nominais (a API
              conta todas, inclusive simbólicas), e a API do Senado não expõe total anual
              confiável.
            </p>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <span className="font-semibold text-[#383838]">Legenda:</span>
              <Badge status="completo" /> ≥95%
              <Badge status="quase" /> 80–95%
              <Badge status="parcial" /> &lt;80%
              <Badge status="superset" /> principais + sub-documentos
              <Badge status="sem_referencia" /> sem total oficial
            </div>
          </div>

          {/* 1. Proposições */}
          <Section n={1} title="Proposições" nota={data.proposicoes.nota_superset}>
            <div className="mp-card overflow-x-auto bg-white p-5">
              <p className="mb-3 text-[13px] font-semibold text-[#383838]/70">
                Câmara — Nosso × Oficial × % de cobertura
              </p>
              <table className="w-full text-right text-[13px]">
                <thead>
                  <tr className="border-b border-[#383838]/10 text-[#383838]/50">
                    <th className="py-2 text-left font-semibold">Ano</th>
                    <th className="px-3 py-2 font-semibold">Nosso</th>
                    <th className="px-3 py-2 font-semibold">Oficial (API)</th>
                    <th className="px-3 py-2 font-semibold">%</th>
                    <th className="px-3 py-2 text-center font-semibold">Situação</th>
                  </tr>
                </thead>
                <tbody>
                  {data.proposicoes.camara.map((r) => (
                    <tr key={r.year} className="border-b border-[#383838]/5">
                      <td className="py-2 text-left font-semibold text-[#090909]">
                        {r.year}
                      </td>
                      <td className="px-3 py-2 tabular-nums">{num(r.nosso)}</td>
                      <td className="px-3 py-2 tabular-nums text-[#383838]/60">
                        {r.oficial != null ? num(r.oficial) : '—'}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {r.pct != null ? `${r.pct}%` : '—'}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <Badge status={r.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="pt-1 text-[13px] font-semibold text-[#383838]/70">
              Senado — nossa base (a API do Senado não dá total anual confiável)
            </p>
            <YearMatrix
              rows={[{ label: 'Proposições', data: data.proposicoes.senado }]}
            />
          </Section>

          {/* 2. Discursos */}
          <Section n={2} title="Discursos (notas taquigráficas)" nota={data.discursos.nota}>
            <YearMatrix
              rows={[
                { label: 'Câmara', data: data.discursos.camara },
                { label: 'Senado', data: data.discursos.senado },
              ]}
            />
          </Section>

          {/* 3. Votações */}
          <Section n={3} title="Votações nominais" nota={data.votacoes.nota}>
            <YearMatrix
              rows={[
                { label: 'Câmara', data: data.votacoes.camara },
                { label: 'Senado', data: data.votacoes.senado },
              ]}
            />
          </Section>

          {/* 4. Parlamentares */}
          <Section n={4} title="Parlamentares" nota={data.parlamentares.nota}>
            <div className="mp-card overflow-x-auto bg-white p-5">
              <table className="w-full text-right text-[13px]">
                <thead>
                  <tr className="border-b border-[#383838]/10 text-[#383838]/50">
                    <th className="py-2 text-left font-semibold">Casa</th>
                    <th className="px-3 py-2 font-semibold">Nossa base</th>
                    <th className="px-3 py-2 font-semibold">Cadeiras atuais</th>
                    <th className="px-3 py-2 text-center font-semibold">Situação</th>
                  </tr>
                </thead>
                <tbody>
                  {(
                    [
                      ['Deputados', data.parlamentares.deputados],
                      ['Senadores', data.parlamentares.senadores],
                    ] as const
                  ).map(([label, p]) => (
                    <tr key={label} className="border-b border-[#383838]/5">
                      <td className="py-2 text-left font-semibold text-[#090909]">
                        {label}
                      </td>
                      <td className="px-3 py-2 tabular-nums">{num(p.nossa_base)}</td>
                      <td className="px-3 py-2 tabular-nums text-[#383838]/60">
                        {num(p.cadeiras)}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <Badge status={p.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          {/* 5. Completude consolidada */}
          <Section n={5} title="Completude consolidada">
            <div className="mp-card overflow-x-auto bg-white p-5">
              <table className="w-full text-left text-[13px]">
                <thead>
                  <tr className="border-b border-[#383838]/10 text-[#383838]/50">
                    <th className="py-2 font-semibold">Categoria</th>
                    <th className="px-3 py-2 text-center font-semibold">Situação</th>
                    <th className="px-3 py-2 font-semibold">Observação</th>
                  </tr>
                </thead>
                <tbody>
                  {data.consolidado.map((c) => (
                    <tr key={c.categoria} className="border-b border-[#383838]/5">
                      <td className="py-2 pr-3 font-semibold text-[#090909]">
                        {c.categoria}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <Badge status={c.status} />
                      </td>
                      <td className="px-3 py-2 text-[#383838]/70">{c.observacao}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        </>
      )}
    </AdminShell>
  );
}
