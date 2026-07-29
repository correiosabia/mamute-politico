import { AlertTriangle, CircleAlert, CircleCheck, HelpCircle } from 'lucide-react';

import type { CreditsMetrics, CreditStatus } from '@/api/admin';

/**
 * Saldo do OpenRouter no painel de IA (CS-31).
 *
 * Existe porque em 29/07/2026 os créditos zeraram no meio de uma carga de
 * embeddings e o chatbot inteiro saiu do ar — chat e busca vetorial em 402 —
 * sem nenhum sinal prévio. O painel torna isso visível antes de acontecer.
 */

const usd = (v: number | null) =>
  v == null ? '—' : `US$ ${v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const ESTILO: Record<
  CreditStatus,
  { rotulo: string; cor: string; fundo: string; Icone: typeof CircleCheck }
> = {
  ok: { rotulo: 'Saldo saudável', cor: '#15803d', fundo: '#15803d14', Icone: CircleCheck },
  atencao: { rotulo: 'Saldo baixo', cor: '#b45309', fundo: '#b4530914', Icone: AlertTriangle },
  critico: { rotulo: 'Saldo crítico', cor: '#c0392b', fundo: '#c0392b14', Icone: CircleAlert },
  desconhecido: { rotulo: 'Saldo indisponível', cor: '#6b7280', fundo: '#6b728014', Icone: HelpCircle },
};

export function CreditsPanel({ data }: { data: CreditsMetrics }) {
  const { rotulo, cor, fundo, Icone } = ESTILO[data.status] ?? ESTILO.desconhecido;
  const critico = data.status === 'critico';

  return (
    <section aria-label="Créditos do OpenRouter" className="mp-card bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-[18px] font-bold text-[#090909]">Créditos do OpenRouter</h2>
          <p className="mt-0.5 text-[12px] text-[#383838]/50">
            Alimenta o chat e a indexação vetorial. Se zerar, os dois param.
          </p>
        </div>
        <span
          className="flex items-center gap-2 rounded-full px-3 py-1.5 text-[13px] font-semibold"
          style={{ color: cor, background: fundo }}
        >
          <Icone className="h-4 w-4" aria-hidden />
          {rotulo}
        </span>
      </div>

      {!data.disponivel ? (
        <p className="mt-5 text-[14px] text-[#383838]/70">
          Não foi possível consultar o saldo agora. O painel volta a mostrar assim que
          o OpenRouter responder — isso não afeta o funcionamento do chat.
        </p>
      ) : (
        <>
          <div className="mt-5 grid grid-cols-2 gap-4 md:grid-cols-4">
            <div>
              <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">
                Disponível
              </p>
              <p className="mt-1 text-[26px] font-bold" style={{ color: cor }}>
                {usd(data.disponivel_usd)}
              </p>
            </div>
            <div>
              <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">
                Comprado
              </p>
              <p className="mt-1 text-[26px] font-bold text-[#090909]">
                {usd(data.total_credits_usd)}
              </p>
            </div>
            <div>
              <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">
                Gasto — chatbot
              </p>
              <p className="mt-1 text-[26px] font-bold text-[#090909]">{usd(data.chatbot_usd)}</p>
            </div>
            <div>
              <p className="text-[12px] font-semibold uppercase tracking-wide text-[#383838]/50">
                Gasto — embeddings
              </p>
              <p className="mt-1 text-[26px] font-bold text-[#090909]">{usd(data.embeddings_usd)}</p>
            </div>
          </div>

          {critico && (
            <p className="mt-5 rounded-lg bg-[#c0392b14] p-4 text-[14px] leading-relaxed text-[#c0392b]">
              <strong>Reponha o saldo agora.</strong> Quando os créditos zeram, o chat para
              de responder para todos os usuários e a indexação de novos discursos é
              interrompida.{' '}
              <a
                href="https://openrouter.ai/settings/credits"
                target="_blank"
                rel="noreferrer"
                className="font-bold underline"
              >
                Repor no OpenRouter
              </a>
            </p>
          )}

          <p className="mt-4 text-[12px] leading-relaxed text-[#383838]/50">
            Alerta por e-mail aos administradores abaixo de {usd(data.limiar_atencao_usd)}, e
            nível crítico em {usd(data.limiar_critico_usd)} ou menos. O gasto com embeddings é
            derivado: o provedor não separa por finalidade, então sai da diferença entre o
            total consumido e o custo medido do chatbot.
          </p>
        </>
      )}
    </section>
  );
}
