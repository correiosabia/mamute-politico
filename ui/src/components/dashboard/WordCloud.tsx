import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { fetchWordCloudTermsPublic, listParliamentarianSpeechAnalysis } from '@/api/endpoints';
import type { SpeechAnalysisSummaryOut } from '@/api/types';
import { Loader2 } from 'lucide-react';
import {
  FALLBACK_TERM_LISTS,
  buildTermLists,
  filterWordCloudTerm,
  type WordCloudTermLists,
} from './wordCloudTerms';

interface CloudWord {
  text: string;
  frequency: number;
  rank: number;
}

function extractWordsFromAnalysis(
  analysisSummaries: SpeechAnalysisSummaryOut[],
  lists: WordCloudTermLists,
  maxWords = 20
): CloudWord[] {
  const aggregated = new Map<string, { frequency: number; rank: number }>();

  for (const analysis of analysisSummaries) {
    const keyword = analysis.primary_keyword;
    if (!keyword) continue;

    const rawTerm = keyword.term || keyword.keyword;
    if (!rawTerm) continue;

    const term = filterWordCloudTerm(rawTerm, lists);
    if (!term) continue;

    const current = aggregated.get(term);
    if (current) {
      current.frequency += keyword.frequency ?? 0;
      current.rank = Math.min(current.rank, keyword.rank ?? Number.MAX_SAFE_INTEGER);
    } else {
      aggregated.set(term, {
        frequency: keyword.frequency ?? 0,
        rank: keyword.rank ?? Number.MAX_SAFE_INTEGER,
      });
    }
  }

  return Array.from(aggregated.entries())
    .map(([text, values]) => ({
      text,
      frequency: values.frequency,
      rank: Number.isFinite(values.rank) ? values.rank : 999,
    }))
    .sort((a, b) => b.frequency - a.frequency || a.rank - b.rank)
    .slice(0, maxWords);
}

function formatTemaForPrompt(term: string): string {
  return term
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
}

function buildPesquisaPrompt(parlamentarNome: string, tema: string): string {
  const nome = parlamentarNome.trim();
  const temaFmt = formatTemaForPrompt(tema);
  return `O que diz o(a) parlamentar ${nome} sobre ${temaFmt}`;
}

interface WordCloudProps {
  /**
   * Código externo (Câmara/Senado) — é a chave do endpoint de análises que
   * alimenta a nuvem.
   */
  parliamentarianCode?: number;
  /**
   * Id INTERNO do banco — é ele que vira filtro do chat na Pesquisa IA.
   * Confundir os dois foi o bug do "fui na palavra da nuvem e diz que não tem
   * a palavra": o código externo era enviado como filtro e não casava com
   * discurso nenhum.
   */
  parliamentarianId?: number;
  parlamentarNome?: string;
}

export function WordCloud({
  parliamentarianCode,
  parliamentarianId,
  parlamentarNome,
}: WordCloudProps) {
  const navigate = useNavigate();
  const { data: analysisSummaries, isLoading, isError } = useQuery({
    queryKey: ['analysis-parliamentarian', parliamentarianCode],
    queryFn: () =>
      listParliamentarianSpeechAnalysis(parliamentarianCode!, {
        page: 1,
        page_size: 100,
      }),
    enabled: parliamentarianCode != null && parliamentarianCode > 0,
  });

  // Listas geridas em Configurações gerais. Globais e de mudança rara, por isso
  // cache longo. Se a chamada falhar, cai no fallback embutido: nuvem sem
  // filtro nenhum é pior que nuvem com filtro desatualizado.
  const { data: termsPayload } = useQuery({
    queryKey: ['word-cloud-terms'],
    queryFn: fetchWordCloudTermsPublic,
    staleTime: 30 * 60 * 1000,
    retry: false,
  });

  const termLists = useMemo(
    () => (termsPayload ? buildTermLists(termsPayload) : FALLBACK_TERM_LISTS),
    [termsPayload]
  );

  const words = useMemo(() => {
    if (!analysisSummaries?.length) return [];
    return extractWordsFromAnalysis(analysisSummaries, termLists);
  }, [analysisSummaries, termLists]);

  if (parliamentarianCode == null || parliamentarianCode <= 0) {
    return (
      <div className="flex flex-wrap items-center justify-center gap-3 p-4 text-muted-foreground text-sm">
        Selecione um parlamentar para ver os temas dos discursos.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span>Carregando...</span>
      </div>
    );
  }

  if (isError || !words.length) {
    return (
      <div className="flex flex-wrap items-center justify-center gap-3 p-4 text-muted-foreground text-sm">
        Nenhuma análise de discurso encontrada para este parlamentar.
      </div>
    );
  }

  const maxFrequency = Math.max(...words.map((p) => p.frequency));
  const minFrequency = Math.min(...words.map((p) => p.frequency));
  const frequencyRange = maxFrequency - minFrequency || 1;
  const maxRank = Math.max(...words.map((p) => p.rank));
  const minRank = Math.min(...words.map((p) => p.rank));
  const rankRange = maxRank - minRank || 1;

  const getWeight = (frequency: number, rank: number) => {
    const normalizedFrequency = (frequency - minFrequency) / frequencyRange;
    const normalizedRank = (maxRank - rank) / rankRange;
    return normalizedFrequency * 0.75 + normalizedRank * 0.25;
  };

  const getFontSize = (frequency: number, rank: number) => {
    const weight = getWeight(frequency, rank);
    return 14 + weight * 30;
  };

  // const getOpacity = (frequency: number, rank: number) => {
  //   const weight = getWeight(frequency, rank);
  //   return 0.45 + weight * 0.55;
  // };

  const colors = [
    'text-primary',
    'text-accent',
    'text-info',
    'text-warning',
    'text-success',
  ];

  const handleWordNavigate = (tema: string) => {
    if (!parlamentarNome?.trim()) {
      toast.error('Nome do parlamentar indisponível para montar a pergunta.');
      return;
    }
    const pergunta = buildPesquisaPrompt(parlamentarNome, tema);
    const params = new URLSearchParams({
      pergunta,
      autoSend: '1',
      // O tema segue estruturado até o backend: lá ele vira condição
      // obrigatória na busca (a mesma régua que montou a nuvem).
      tema,
    });
    // O nome dentro do texto da pergunta não restringe a busca vetorial: quem
    // faz isso é o filtro por id do outro lado.
    if (parliamentarianId != null && parliamentarianId > 0) {
      params.set('parlamentarId', String(parliamentarianId));
    }
    navigate({ pathname: '/pesquisa', search: params.toString() });
  };

  return (
    <div className="flex flex-wrap items-center justify-center gap-3 p-4">
      {words.map((word, index) => (
        <span
          key={word.text}
          role="button"
          tabIndex={0}
          className={`${colors[index % colors.length]} font-medium uppercase hover:scale-110 transition-transform cursor-pointer select-none rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2`}
          style={{
            fontSize: `${getFontSize(word.frequency, word.rank)}px`,
            // opacity: getOpacity(word.frequency, word.rank),
          }}
          onClick={() => handleWordNavigate(word.text)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              handleWordNavigate(word.text);
            }
          }}
        >
          {word.text}{' '}
          <small>
            <small>
              <small>
                <small>({word.frequency})</small>
              </small>
            </small>
          </small>
        </span>
      ))}
    </div>
  );
}
