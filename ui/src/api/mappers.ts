import type { ParliamentarianOut, ParliamentarianDetailOut, PropositionOut, RollCallVoteOut, SpeechesTranscriptOut } from './types';
import type { GabineteDetalhes, Parlamentar, Proposicao, RedeSocial, Votacao, Discurso } from '@/types/parlamentar';

function pickPhotoUrl(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function getPhotoUrlFromDetails(details: Record<string, unknown> | null | undefined): string | undefined {
  if (!details || typeof details !== 'object') return undefined;

  const direct = pickPhotoUrl(details['UrlFotoParlamentar']);
  if (direct) return direct;

  const topLevelFoto = pickPhotoUrl(details['urlFoto']);
  if (topLevelFoto) return topLevelFoto;

  const ultimoStatus = toRecordOrUndefined(details['ultimoStatus']);
  const camaraFoto = pickPhotoUrl(ultimoStatus?.['urlFoto']);
  if (camaraFoto) return camaraFoto;

  const identificacao = toRecordOrUndefined(details['IdentificacaoParlamentar']);
  const identificacaoFoto = pickPhotoUrl(identificacao?.['UrlFotoParlamentar']);
  if (identificacaoFoto) return identificacaoFoto;

  const lista = toRecordOrUndefined(details['lista']);
  const listaIdent = toRecordOrUndefined(lista?.['IdentificacaoParlamentar']);
  const urlLista = pickPhotoUrl(listaIdent?.['UrlFotoParlamentar']);
  if (urlLista) return urlLista;

  const detalhe = toRecordOrUndefined(details['detalhe']);
  const detalheIdent = toRecordOrUndefined(detalhe?.['IdentificacaoParlamentar']);
  const urlDetalhe = pickPhotoUrl(detalheIdent?.['UrlFotoParlamentar']);
  if (urlDetalhe) return urlDetalhe;

  return undefined;
}

function partidoFromSigla(sigla: string | null | undefined): { sigla: string; nome: string } {
  if (!sigla) return { sigla: '—', nome: '—' };
  return { sigla, nome: sigla };
}

function normalizeStatusText(status: string): string {
  return status
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

function situacaoFromStatus(
  status: string | null | undefined,
  options?: { defaultWhenMissing?: Parlamentar['situacao'] },
): Parlamentar['situacao'] {
  if (!status) return options?.defaultWhenMissing ?? 'Exercício';
  const s = normalizeStatusText(status);
  if (s.includes('licenciado')) return 'Licenciado';
  if (s.includes('fim de mandato') || s.includes('vacancia')) return 'Fim de mandato';
  if (s.includes('afastado') || s.includes('fora de exercicio')) return 'Afastado';
  return 'Exercício';
}

export function isEmExercicio(situacao: Parlamentar['situacao']): boolean {
  return situacao === 'Exercício';
}

function casaFromType(type: string | null | undefined): Parlamentar['casa'] {
  if (!type) return 'camara';
  const t = type.toLowerCase();
  if (t.includes('senador') || t.includes('senado')) return 'senado';
  return 'camara';
}

function toNumberOrUndefined(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return undefined;
}

function toRecordOrUndefined(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  return value as Record<string, unknown>;
}

function getCamaraLegislatura(details: Record<string, unknown> | null | undefined): number | undefined {
  if (!details) return undefined;
  const ultimoStatus = toRecordOrUndefined(details['ultimoStatus']);
  const fromUltimoStatus = toNumberOrUndefined(ultimoStatus?.['idLegislatura']);
  if (fromUltimoStatus !== undefined) return fromUltimoStatus;

  return toNumberOrUndefined(details['idLegislatura']);
}

const SENADO_DIRECT_KEYS = [
  'Legislatura',
  'legislatura',
  'NumeroLegislatura',
  'numeroLegislatura',
  'CodigoLegislatura',
  'codLegislatura',
  'idLegislatura',
  'id_legislatura',
] as const;

function findSenadoLegislaturaInObject(obj: Record<string, unknown>): number | undefined {
  const values: number[] = [];
  const directCandidates = SENADO_DIRECT_KEYS.map((key) => obj[key]);

  for (const candidate of directCandidates) {
    const parsed = toNumberOrUndefined(candidate);
    if (parsed !== undefined) values.push(parsed);
  }

  // Senado payloads often keep current legislatura under mandato branches
  // such as Primeira/SegundaLegislaturaDoMandato.NumeroLegislatura.
  for (const [key, value] of Object.entries(obj)) {
    if (!key.toLowerCase().includes('legislaturadomandato')) continue;
    const mandatoLegObj = toRecordOrUndefined(value);
    if (!mandatoLegObj) continue;
    const numero = toNumberOrUndefined(mandatoLegObj['NumeroLegislatura']);
    if (numero !== undefined) values.push(numero);
    const nestedParsed = findSenadoLegislaturaInObject(mandatoLegObj);
    if (nestedParsed !== undefined) values.push(nestedParsed);
  }

  const nestedCandidates: unknown[] = [
    obj['ultimoStatus'],
    obj['IdentificacaoParlamentar'],
    obj['Mandato'],
    obj['Mandatos'],
  ];

  for (const nested of nestedCandidates) {
    const nestedObj = toRecordOrUndefined(nested);
    if (!nestedObj) continue;
    const parsed = findSenadoLegislaturaInObject(nestedObj);
    if (parsed !== undefined) values.push(parsed);
  }

  if (values.length > 0) {
    return Math.max(...values);
  }

  return undefined;
}

function getLegislatura(o: ParliamentarianOut): number {
  const casa = casaFromType(o.type);
  const details = toRecordOrUndefined(o.details);

  if (casa === 'camara') {
    const camaraLegislatura = getCamaraLegislatura(details);
    if (camaraLegislatura !== undefined) return camaraLegislatura;
  } else {
    const senadoRoots = [details?.['lista'], details?.['detalhe']];
    for (const root of senadoRoots) {
      const rootObj = toRecordOrUndefined(root);
      if (!rootObj) continue;
      const parsed = findSenadoLegislaturaInObject(rootObj);
      if (parsed !== undefined) return parsed;
    }
  }

  // Backward-compatible fallback while APIs/ETL fully expose this consistently.
  return -1;
}

function toStringOrUndefined(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function getCamaraStatus(details: Record<string, unknown> | undefined, topLevelStatus: string | null | undefined): string | undefined {
  const fromTopLevel = toStringOrUndefined(topLevelStatus);
  if (fromTopLevel) return fromTopLevel;

  const ultimoStatus = toRecordOrUndefined(details?.['ultimoStatus']);
  return toStringOrUndefined(ultimoStatus?.['situacao']);
}

function findSenadoStatusInObject(obj: Record<string, unknown>): string | undefined {
  const directCandidates = [
    obj['status'],
    obj['situacao'],
    obj['Situacao'],
    obj['SituacaoParlamentar'],
    obj['DescricaoSituacao'],
    obj['DescricaoStatus'],
  ];

  for (const candidate of directCandidates) {
    const parsed = toStringOrUndefined(candidate);
    if (parsed) return parsed;
  }

  const nestedCandidates: unknown[] = [
    obj['IdentificacaoParlamentar'],
    obj['Mandato'],
    obj['Mandatos'],
    obj['DadosBasicosParlamentar'],
  ];

  for (const nested of nestedCandidates) {
    const nestedObj = toRecordOrUndefined(nested);
    if (!nestedObj) continue;
    const parsed = findSenadoStatusInObject(nestedObj);
    if (parsed) return parsed;
  }

  return undefined;
}

function getSituacao(o: ParliamentarianOut): Parlamentar['situacao'] {
  const casa = casaFromType(o.type);
  const details = toRecordOrUndefined(o.details);

  if (casa === 'camara') {
    const status = getCamaraStatus(details, o.status);
    const missingData = !o.name?.trim() || !o.party?.trim();
    const defaultWhenMissing = missingData && !status ? 'Fim de mandato' : 'Exercício';
    return situacaoFromStatus(status, { defaultWhenMissing });
  }

  const senadoRoots = [details?.['lista'], details?.['detalhe']];
  for (const root of senadoRoots) {
    const rootObj = toRecordOrUndefined(root);
    if (!rootObj) continue;
    const parsed = findSenadoStatusInObject(rootObj);
    if (parsed) return situacaoFromStatus(parsed);
  }

  // Senado source list is "ListaParlamentarEmExercicio"; default remains active.
  return 'Exercício';
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

function formatNaturalidade(city?: string | null, state?: string | null): string | undefined {
  const parts = [city, state].filter((value): value is string => Boolean(value?.trim()));
  return parts.length > 0 ? parts.join(', ') : undefined;
}

function buildGabineteDetalhes(o: ParliamentarianOut): GabineteDetalhes | undefined {
  const detalhes: GabineteDetalhes = {
    predio: o.office_building?.trim() || undefined,
    sala: o.office_number?.trim() || undefined,
    andar: o.office_floor?.trim() || undefined,
    nome: o.office_name?.trim() || undefined,
  };
  return Object.values(detalhes).some(Boolean) ? detalhes : undefined;
}

function mapSocialNetworks(o: ParliamentarianDetailOut): RedeSocial[] | undefined {
  const redes = (o.social_networks ?? [])
    .map((rede) => ({
      name: rede.name?.trim() || 'Rede social',
      profileUrl: rede.profile_url?.trim() || undefined,
    }))
    .filter((rede) => rede.profileUrl);
  return redes.length > 0 ? redes : undefined;
}

export function mapParliamentarianOutToParlamentar(o: ParliamentarianOut | ParliamentarianDetailOut): Parlamentar {
  const partido = partidoFromSigla(o.party ?? undefined);
  const gabinete = [o.office_building, o.office_name, o.office_number]
    .filter(Boolean)
    .join(' ') || undefined;
  const foto = o.photo_url ?? getPhotoUrlFromDetails(o.details) ?? '';
  const legislatura = getLegislatura(o);
  const gabineteDetalhes = buildGabineteDetalhes(o);
  const redesSociais = 'social_networks' in o ? mapSocialNetworks(o) : undefined;

  return {
    id: String(o.id),
    nome: o.name ?? '—',
    nomeCompleto: o.full_name ?? o.name ?? '—',
    foto,
    partido,
    uf: o.state_elected ?? '—',
    casa: casaFromType(o.type),
    legislatura,
    email: o.email ?? undefined,
    telefone: o.telephone ?? undefined,
    gabinete: gabinete || undefined,
    gabineteDetalhes,
    naturalidade: formatNaturalidade(o.city_of_birth, o.state_of_birth),
    escolaridade: o.education?.trim() || undefined,
    site: o.site?.trim() || undefined,
    emailGabinete: o.office_email?.trim() || undefined,
    biografiaLink: o.biography_link?.trim() || undefined,
    biografiaTexto: o.biography_text?.trim() || undefined,
    redesSociais,
    situacao: getSituacao(o),
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
  const ementa = o.summary?.trim() || o.proposition_description?.trim() || '—';
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
