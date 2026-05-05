import { useQueries } from '@tanstack/react-query';
import { listPropositions, listRollCallVotes } from '@/api/endpoints';
import { votoFromApi } from '@/api/mappers';
import type { RollCallVoteOut } from '@/api/types';
import { Loader2 } from 'lucide-react';
import iconProjeto from '@/assets/icon-timeline-projeto.svg';
import iconVotacaoAprovado from '@/assets/icon-timeline-votacao-aprovado.svg';
import iconVotacaoRejeitado from '@/assets/icon-timeline-votacao-rejeitado.svg';

interface TimelineItem {
  id: string;
  tipo: 'proposicao' | 'votacao';
  titulo: string;
  descricao: string;
  data: string;
  autor: string;
  status: string;
  link?: string;
}

function formatVoteParliamentarianAutor(v: RollCallVoteOut): string {
  const nome = v.parliamentarian_name?.trim();
  const partido = v.parliamentarian_party?.trim();
  const uf = v.parliamentarian_state_elected?.trim();
  if (nome && partido && uf) return `${nome} ${partido} - ${uf}`;
  if (nome && partido) return `${nome} ${partido}`;
  if (nome) return nome;
  return '—';
}

function extractAutor(details: Record<string, unknown> | null | undefined): string {
  if (!details) return '—';
  const processo = details['processo'] as Record<string, unknown> | undefined;
  const documento = processo?.['documento'] as Record<string, unknown> | undefined;
  const autoria = documento?.['autoria'] as Array<Record<string, unknown>> | undefined;
  if (autoria && autoria.length > 0) {
    const a = autoria[0];
    const nome = a['autor'] as string | undefined;
    const partido = a['siglaPartido'] as string | undefined;
    const uf = a['uf'] as string | undefined;
    if (nome) return partido && uf ? `${nome} ${partido} - ${uf}` : nome;
  }
  return '—';
}

function getItemIcon(item: TimelineItem): string {
  if (item.tipo === 'proposicao') return iconProjeto;
  if (item.status === 'Sim') return iconVotacaoAprovado;
  if (item.status === 'Não') return iconVotacaoRejeitado;
  return iconVotacaoAprovado;
}

function getBadgeClass(item: TimelineItem): string {
  if (item.tipo === 'proposicao') return 'bg-[#1b76ff]';
  if (item.tipo === 'votacao') {
    if (item.status === 'Sim') return 'bg-[#09e03b]';
    if (item.status === 'Não') return 'bg-[#ff0004]';
    if (item.status === 'Abstenção') return 'bg-[#f59e0b]';
    return 'bg-[#6b7280]';
  }
  return 'bg-[#1b76ff]';
}

const VOTO_LABELS_NO_TITLECASE = new Set(['Sim', 'Não', 'Abstenção', 'Obstrução', 'Ausente']);

function toTitleCase(str: string): string {
  if (!str || str === '—') return str;
  if (VOTO_LABELS_NO_TITLECASE.has(str)) return str;
  if (str === 'Aprovado' || str === 'Rejeitado') return str;
  return str.toLowerCase().split(' ').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function getStatusClass(item: TimelineItem): string {
  if (item.tipo === 'votacao') {
    if (item.status === 'Sim') return 'text-[#09e03b]';
    if (item.status === 'Não') return 'text-[#ff0004]';
    if (item.status === 'Abstenção') return 'text-[#d97706]';
    return 'text-[#383838]';
  }
  if (item.status === 'Aprovado') return 'text-[#09e03b]';
  if (item.status === 'Rejeitado') return 'text-[#ff0004]';
  return 'text-[#383838]';
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '—';
  try {
    return new Date(dateStr + 'T00:00:00').toLocaleDateString('pt-BR');
  } catch {
    return dateStr;
  }
}

export function Timeline() {
  const queryParams = { limit: 20, offset: 0 } as const;
  const [propositionsQuery, votesQuery] = useQueries({
    queries: [
      {
        queryKey: ['propositions', 'timeline', queryParams],
        queryFn: () => listPropositions(queryParams),
      },
      {
        queryKey: ['roll-call-votes', 'timeline', queryParams],
        queryFn: () => listRollCallVotes(queryParams),
      },
    ],
  });

  const propositions = propositionsQuery.data ?? [];
  const votes = votesQuery.data ?? [];

  const timelineItems: TimelineItem[] = [
    ...propositions.map((p) => ({
      id: `p-${p.id}`,
      tipo: 'proposicao' as const,
      titulo: `${p.proposition_acronym ?? 'PL'} ${p.proposition_number ?? ''}/${p.presentation_year ?? ''}`.trim(),
      descricao: p.proposition_description ?? p.summary ?? '—',
      data: p.presentation_date ?? p.created_at?.slice(0, 10) ?? '',
      autor: extractAutor(p.details),
      status: p.current_status ?? '—',
      link: p.link ?? undefined,
    })),
    ...votes.map((v) => ({
      id: `v-${v.id}`,
      tipo: 'votacao' as const,
      titulo: v.proposition_title?.trim() || `Votação #${v.proposition_id}`,
      descricao: v.description?.trim() || '—',
      data: v.date_vote?.slice(0, 10) ?? v.created_at?.slice(0, 10) ?? '',
      autor: formatVoteParliamentarianAutor(v),
      status: votoFromApi(v.vote),
      link: v.proposition_votes_link ?? v.link ?? undefined,
    })),
  ]
    .filter((i) => i.data)
    .sort((a, b) => {
      const aTs = Date.parse(a.data);
      const bTs = Date.parse(b.data);
      if (Number.isNaN(aTs) || Number.isNaN(bTs)) {
        return b.data.localeCompare(a.data);
      }
      return bTs - aTs;
    });

  const isLoading = propositionsQuery.isLoading || votesQuery.isLoading;
  const hasNoData = propositions.length === 0 && votes.length === 0;
  const isError = propositionsQuery.isError && votesQuery.isError;

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-[#383838]/60">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span>Carregando linha do tempo...</span>
      </div>
    );
  }

  if (isError && hasNoData) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[#383838]/60">
        Falha ao carregar a linha do tempo.
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto space-y-[26px] pr-[6px] mp-timeline-scroll">
      {timelineItems.length === 0 ? (
        <div className="flex h-full items-center justify-center text-sm text-[#383838]/60">
          Nenhum item na linha do tempo.
        </div>
      ) : (
        timelineItems.map((item) => (
          <div
            key={item.id}
            role={item.link ? 'link' : undefined}
            tabIndex={item.link ? 0 : -1}
            onClick={() => {
              if (!item.link) return;
              window.open(item.link, '_blank', 'noopener,noreferrer');
            }}
            onKeyDown={(e) => {
              if (!item.link) return;
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                window.open(item.link, '_blank', 'noopener,noreferrer');
              }
            }}
            className={[
              'flex items-start gap-5 rounded-[28px] bg-white px-6 py-[22px] shadow-[0_4px_4px_rgba(0,0,0,0.25)]',
              item.link
                ? 'cursor-pointer transition-colors hover:bg-[#f9f9f9] focus:outline-none focus:ring-2 focus:ring-[#1b76ff] focus:ring-offset-2'
                : 'cursor-default',
            ].join(' ')}
          >
            {/* Icon */}
            <div className="shrink-0 flex items-start pt-0.5">
              <img src={getItemIcon(item)} alt="" className="w-[38px] h-[42px] object-contain" />
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              {/* Row 1: bill + badge + status */}
              <div className="mb-1.5 flex min-w-0 flex-wrap items-center gap-2">
                <span className="min-w-0 truncate text-[18px] font-semibold leading-none text-[#383838]">
                  {item.titulo}
                </span>
                <span
                  className={`shrink-0 rounded-full px-3 py-0.5 text-[11px] font-bold text-white ${getBadgeClass(item)}`}
                >
                  {item.tipo === 'proposicao' ? 'PROJETO' : 'VOTAÇÃO'}
                </span>
                <span
                  className={`basis-full text-[13px] font-semibold truncate md:basis-auto md:max-w-[140px] ${getStatusClass(item)}`}
                >
                  {toTitleCase(item.status)}
                </span>
              </div>

              {/* Row 2: description */}
              <p className="text-[11px] text-[#383838] line-clamp-1 mb-2 leading-snug">
                {item.descricao}
              </p>

              {/* Row 3: author + date */}
              <div className="flex min-w-0 items-center justify-between gap-3">
                <span className="min-w-0 truncate text-[13px] font-semibold text-[#383838]">{item.autor}</span>
                <span className="text-[13px] font-semibold text-[#383838]">
                  {formatDate(item.data)}
                </span>
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
