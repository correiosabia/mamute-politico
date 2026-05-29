import type { ParliamentarianOut, PropositionOut, RollCallVoteOut, SpeechesTranscriptOut } from './types';
import type { Parlamentar, Proposicao, Votacao, Discurso } from '@/types/parlamentar';

function getPhotoUrlFromDetails(details: Record<string, unknown> | null | undefined): string | undefined {
  if (!details || typeof details !== 'object') return undefined;
  const direct = details['UrlFotoParlamentar'];
  if (typeof direct === 'string' && direct) return direct;
  const lista = details['lista'] as Record<string, unknown> | undefined;
  const listaIdent = lista?.['IdentificacaoParlamentar'] as Record<string, unknown> | undefined;
  const urlLista = listaIdent?.['UrlFotoParlamentar'];
  if (typeof urlLista === 'string' && urlLista) return urlLista;
  const detalhe = details['detalhe'] as Record<string, unknown> | undefined;
  const detalheIdent = detalhe?.['IdentificacaoParlamentar'] as Record<string, unknown> | undefined;
  const urlDetalhe = detalheIdent?.['UrlFotoParlamentar'];
  if (typeof urlDetalhe === 'string' && urlDetalhe) return urlDetalhe;
  const ultimoStatus = details['ultimoStatus'] as Record<string, unknown> | undefined;
  const urlCamara = ultimoStatus?.['urlFoto'];
  if (typeof urlCamara === 'string' && urlCamara) return urlCamara;
  return undefined;
}

function partidoFromSigla(sigla: string | null | undefined): { sigla: string; nome: string } {
  if (!sigla) return { sigla: '—', nome: '—' };
  return { sigla, nome: sigla };
}

function situacaoFromStatus(status: string | null | undefined): Parlamentar['situacao'] {
  if (!status) return 'Exercício';
  const s = status.toLowerCase();
  if (s.includes('licenciado')) return 'Licenciado';
  if (s.includes('afastado')) return 'Afastado';
  return 'Exercício';
}

function casaFromType(type: string | null | undefined): Parlamentar['casa'] {
  if (!type) return 'camara';
  const t = type.toLowerCase();
  if (t.includes('senador') || t.includes('senado')) return 'senado';
  return 'camara';
}

export function votoFromApi(vote: string | null | undefined): Votacao['voto'] {
  if (!vote) return 'Abstenção';
  const v = vote.toLowerCase();
  if (v.includes('sim') || v === 'yes') return 'Sim';
  if (v.includes('não') || v.includes('nao') || v === 'no') return 'Não';
  if (v.includes('abstenção') || v.includes('abstencao')) return 'Abstenção';
  if (v.includes('obstrução') || v.includes('obstrucao')) return 'Obstrução';
  if (v.includes('ausente')) return 'Ausente';
  return 'Abstenção';
}

export function mapParliamentarianOutToParlamentar(o: ParliamentarianOut): Parlamentar {
  const partido = partidoFromSigla(o.party ?? undefined);
  const gabinete = [o.office_building, o.office_name, o.office_number]
    .filter(Boolean)
    .join(' ') || undefined;
  const foto = o.photo_url ?? getPhotoUrlFromDetails(o.details) ?? '';
  return {
    id: String(o.id),
    nome: o.name ?? '—',
    nomeCompleto: o.full_name ?? o.name ?? '—',
    foto,
    partido,
    uf: o.state_elected ?? '—',
    casa: casaFromType(o.type),
    legislatura: 57,
    email: o.email ?? undefined,
    telefone: o.telephone ?? undefined,
    gabinete: gabinete || undefined,
    situacao: situacaoFromStatus(o.status),
  };
}

function getAutorFromDetails(details: Record<string, unknown> | null | undefined): string {
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

export function mapPropositionOutToProposicao(o: PropositionOut): Proposicao {
  const ementa = o.proposition_description ?? o.summary ?? '—';
  return {
    id: String(o.id),
    tipo: o.proposition_acronym ?? '—',
    numero: o.proposition_number ?? 0,
    ano: o.presentation_year ?? 0,
    link: o.link ?? undefined,
    ementa,
    dataApresentacao: o.presentation_date ?? '',
    situacao: o.current_status ?? '—',
    tema: '—',
    autor: getAutorFromDetails(o.details),
  };
}

export function mapRollCallVoteOutToVotacao(o: RollCallVoteOut): Votacao {
  const propositionLabel = o.proposition_title?.trim() || `Proposição #${o.proposition_id}`;
  return {
    id: String(o.id),
    proposicao: propositionLabel,
    proposicaoLink: o.proposition_votes_link ?? undefined,
    data: o.date_vote?.slice(0, 10) ?? o.created_at?.slice(0, 10) ?? '',
    voto: votoFromApi(o.vote),
    descricao: o.description?.trim() || '—',
  };
}

export function mapSpeechesTranscriptOutToDiscurso(o: SpeechesTranscriptOut): Discurso {
  return {
    id: String(o.id),
    data: o.date?.slice(0, 10) ?? '',
    resumo: o.summary ?? '—',
    tema: '—',
    palavrasChave: [],
  };
}
