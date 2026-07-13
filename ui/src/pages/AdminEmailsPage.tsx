import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { MetricsLayout } from '@/components/admin/MetricsLayout';
import { useEmails } from '@/hooks/useMetrics';
import { num } from '@/lib/adminFormat';
import type { EmailSendStatus } from '@/api/admin';
import { cn } from '@/lib/utils';

const STATUS_LABELS: Record<EmailSendStatus, string> = {
  sent: 'Enviado',
  error: 'Erro',
  skipped_no_favorites: 'Pulado (sem favoritos)',
  skipped_no_activity: 'Pulado (sem atividade)',
};

const STATUS_STYLES: Record<EmailSendStatus, string> = {
  sent: 'bg-[#e6f4ea] text-[#1e7e34]',
  error: 'bg-[#fdecea] text-[#c0392b]',
  skipped_no_favorites: 'bg-[#f4f4f4] text-[#383838]/60',
  skipped_no_activity: 'bg-[#f4f4f4] text-[#383838]/60',
};

const dt = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—';

const d = (iso: string | null) =>
  iso ? new Date(`${iso}T12:00:00`).toLocaleDateString('pt-BR') : '—';

export default function AdminEmailsPage() {
  const { data, isLoading } = useEmails();

  return (
    <MetricsLayout
      title="E-mails"
      subtitle="Relatórios enviados aos usuários e próximos disparos previstos."
    >
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
              <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">
                Enviados
              </p>
              <p className="mt-1 text-[26px] font-bold text-[#090909]">
                {num(data.kpis.enviados)}
              </p>
            </div>
            <div className="mp-card bg-white p-5">
              <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">
                Erros
              </p>
              <p className="mt-1 text-[26px] font-bold text-[#090909]">
                {num(data.kpis.erros)}
              </p>
            </div>
            <div className="mp-card bg-white p-5">
              <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">
                Pulados
              </p>
              <p className="mt-1 text-[26px] font-bold text-[#090909]">
                {num(data.kpis.pulados)}
              </p>
            </div>
            <div className="mp-card bg-white p-5">
              <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">
                Último envio
              </p>
              <p className="mt-1 text-[20px] font-bold text-[#090909]">
                {dt(data.kpis.ultimo_envio)}
              </p>
            </div>
          </div>

          <div className="mp-card overflow-x-auto bg-white p-6">
            <h2 className="mb-1 text-[18px] font-bold text-[#090909]">Próximos envios</h2>
            <p className="mb-4 text-[12px] text-[#383838]/50">
              Previsão pelo agendamento (11:00 UTC / 08:00 BRT) cruzado com a
              periodicidade configurada em cada plano. Projetos sem parlamentares
              favoritados ou sem atividade no período são pulados na hora do envio.
            </p>
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr className="border-b border-[#383838]/10 text-[11px] uppercase tracking-wide text-[#383838]/50">
                  <th className="py-2 pr-3 font-semibold">Periodicidade</th>
                  <th className="py-2 pr-3 font-semibold">Próximo envio</th>
                  <th className="py-2 pr-3 font-semibold">Planos</th>
                  <th className="py-2 pr-3 text-right font-semibold">Destinatários</th>
                  <th className="py-2 pr-3 text-right font-semibold">Com favoritos</th>
                </tr>
              </thead>
              <tbody>
                {data.proximos.map((p) => (
                  <tr
                    key={p.periodicidade}
                    className={cn(
                      'border-b border-[#383838]/5',
                      p.tiers.length === 0 && 'text-[#383838]/40',
                    )}
                  >
                    <td className="py-2 pr-3 font-medium">{p.periodicidade_label}</td>
                    <td className="py-2 pr-3">
                      {p.tiers.length > 0 ? dt(p.proximo_envio) : '—'}
                    </td>
                    <td className="py-2 pr-3">
                      {p.tiers.length > 0 ? p.tiers.join(', ') : 'Nenhum plano configurado'}
                    </td>
                    <td className="py-2 pr-3 text-right">{num(p.destinatarios)}</td>
                    <td className="py-2 pr-3 text-right">{num(p.com_favoritos)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mp-card overflow-x-auto bg-white p-6">
            <h2 className="mb-1 text-[18px] font-bold text-[#090909]">Histórico</h2>
            <p className="mb-4 text-[12px] text-[#383838]/50">
              Cada tentativa de envio da rotina de notificação (últimos 200 registros).
            </p>
            {!data.log_disponivel ? (
              <p className="text-[14px] text-[#383838]/50">
                Histórico indisponível: a migration do log de envios ainda não foi
                aplicada neste ambiente.
              </p>
            ) : data.historico.length > 0 ? (
              <table className="w-full text-left text-[13px]">
                <thead>
                  <tr className="border-b border-[#383838]/10 text-[11px] uppercase tracking-wide text-[#383838]/50">
                    <th className="py-2 pr-3 font-semibold">Quando</th>
                    <th className="py-2 pr-3 font-semibold">Destinatário</th>
                    <th className="py-2 pr-3 font-semibold">Periodicidade</th>
                    <th className="py-2 pr-3 font-semibold">Período coberto</th>
                    <th className="py-2 pr-3 font-semibold">Status</th>
                    <th className="py-2 pr-3 font-semibold">Detalhe</th>
                  </tr>
                </thead>
                <tbody>
                  {data.historico.map((h) => (
                    <tr key={h.id} className="border-b border-[#383838]/5">
                      <td className="py-2 pr-3 whitespace-nowrap">{dt(h.created_at)}</td>
                      <td className="py-2 pr-3">
                        <Link
                          to={`/admin/metrics/users/${h.projeto_id}`}
                          className="font-medium text-[#1b76ff] no-underline hover:underline"
                        >
                          {h.email}
                        </Link>
                      </td>
                      <td className="py-2 pr-3">{h.periodicidade_label}</td>
                      <td className="py-2 pr-3 whitespace-nowrap">
                        {h.period_start ? `${d(h.period_start)} – ${d(h.period_end)}` : '—'}
                      </td>
                      <td className="py-2 pr-3">
                        <span
                          className={cn(
                            'rounded-full px-2 py-0.5 text-[11px] font-semibold',
                            STATUS_STYLES[h.status] ?? 'bg-[#f4f4f4] text-[#383838]/60',
                          )}
                        >
                          {STATUS_LABELS[h.status] ?? h.status}
                        </span>
                      </td>
                      <td className="py-2 pr-3 text-[#383838]/70">
                        {h.status === 'sent' && h.stats
                          ? [
                              h.stats.proposicoes != null &&
                                `${num(h.stats.proposicoes)} proposições`,
                              h.stats.votacoes != null && `${num(h.stats.votacoes)} votações`,
                              h.stats.discursos != null && `${num(h.stats.discursos)} discursos`,
                            ]
                              .filter(Boolean)
                              .join(' · ')
                          : h.detail ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-[14px] text-[#383838]/50">
                Nenhum envio registrado ainda. O histórico começa a contar a partir do
                primeiro disparo após este deploy.
              </p>
            )}
          </div>
        </>
      )}
    </MetricsLayout>
  );
}
