import { useQuery } from '@tanstack/react-query';
import { listPropositions, listPropositionsByParliamentarian } from '@/api/endpoints';
import { mapPropositionOutToProposicao } from '@/api/mappers';
import { getProposicaoSituacaoTextClass } from '@/lib/proposicaoSituacao';
import { Loader2 } from 'lucide-react';

interface ProposicoesListProps {
  limit?: number;
  parliamentarianId?: string;
}

function toTitleCase(str: string): string {
  if (!str || str === '—') return str;
  return str.toLowerCase().split(' ').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '—';
  try {
    return new Date(dateStr + 'T00:00:00').toLocaleDateString('pt-BR');
  } catch {
    return dateStr;
  }
}

export function ProposicoesList({ limit = 5, parliamentarianId }: ProposicoesListProps) {
  const numericId = parliamentarianId != null && parliamentarianId !== '' ? Number(parliamentarianId) : NaN;
  const isParliamentarianScope = Number.isInteger(numericId) && numericId > 0;

  const { data: rawList, isLoading, isError } = useQuery({
    queryKey: ['propositions', isParliamentarianScope ? 'by-parliamentarian' : 'list', numericId, limit],
    queryFn: () =>
      isParliamentarianScope
        ? listPropositionsByParliamentarian(numericId, { limit })
        : listPropositions({ limit, offset: 0 }),
  });

  const proposicoes = rawList != null ? rawList.map(mapPropositionOutToProposicao) : [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8 gap-2 text-[#383838]/60">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>Carregando...</span>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="text-center py-8 text-[#383838]/60 text-sm">
        Falha ao carregar proposições.
      </div>
    );
  }

  return (
    <div className="space-y-[22px]">
      {proposicoes.map((proposicao) => (
        <div
          key={proposicao.id}
          role={proposicao.link ? 'link' : undefined}
          tabIndex={proposicao.link ? 0 : -1}
          onClick={() => {
            if (!proposicao.link) return;
            window.open(proposicao.link, '_blank', 'noopener,noreferrer');
          }}
          onKeyDown={(e) => {
            if (!proposicao.link) return;
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              window.open(proposicao.link, '_blank', 'noopener,noreferrer');
            }
          }}
          className={[
            'rounded-[28px] bg-white px-7 py-[22px] shadow-[0_4px_4px_rgba(0,0,0,0.25)]',
            proposicao.link
              ? 'cursor-pointer hover:bg-[#f9f9f9] transition-colors focus:outline-none focus:ring-2 focus:ring-[#1b76ff] focus:ring-offset-2'
              : 'cursor-default',
          ].join(' ')}
        >
          {/* Row 1: bill + badge + status */}
          <div className="mb-1.5 flex min-w-0 flex-wrap items-center gap-2">
            <span className="min-w-0 truncate text-[18px] font-semibold leading-none text-[#383838]">
              {proposicao.tipo} {proposicao.numero}/{proposicao.ano}
            </span>
            <span className="shrink-0 rounded-full px-3 py-0.5 text-[11px] font-bold text-white bg-[#1b76ff]">
              PROJETO
            </span>
            <span
              className={`basis-full text-[11px] font-semibold truncate md:basis-auto md:max-w-[140px] ${getProposicaoSituacaoTextClass(proposicao.situacao)}`}
            >
              {toTitleCase(proposicao.situacao)}
            </span>
          </div>

          {/* Description */}
          <p className="text-[11px] text-[#383838] line-clamp-3 mb-2 leading-snug">
            {proposicao.ementa}
          </p>

          {/* Date + Theme */}
          <div className="flex min-w-0 items-center gap-4">
            <span className="text-[11px] font-semibold text-[#383838]">
              {formatDate(proposicao.dataApresentacao)}
            </span>
            {proposicao.tema && proposicao.tema !== '—' && (
              <span className="min-w-0 truncate text-[11px] font-semibold text-[#383838]">{proposicao.tema}</span>
            )}
          </div>
        </div>
      ))}
      {proposicoes.length === 0 && (
        <div className="text-center py-6 text-[#383838]/60 text-sm">
          Nenhuma proposição encontrada.
        </div>
      )}
    </div>
  );
}
