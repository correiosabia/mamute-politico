import { request } from './client';
import type {
  ParliamentarianOut,
  ParliamentarianDetailOut,
  PropositionOut,
  RollCallVoteOut,
  SpeechesTranscriptOut,
  ProjectFavoriteOut,
  AuthorsPropositionOut,
  SpeechAnalysisSummaryOut,
  SpeechAnalysisOut,
  DashboardStatsOut,
  DashboardActivityOut,
} from './types';

export interface ListParliamentariansParams {
  limit?: number;
  offset?: number;
  party?: string;
  type?: Array<'deputado' | 'senado'>;
  situacao?: 'exercicio' | 'afastado' | 'licenciado' | 'fim_de_mandato';
}

export function listParliamentarians(
  params: ListParliamentariansParams = {}
): Promise<ParliamentarianOut[]> {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', String(params.limit));
  if (params.offset != null) sp.set('offset', String(params.offset));
  if (params.party) sp.set('party', params.party);
  if (params.type?.length) {
    params.type.forEach((t) => sp.append('type', t));
  }
  if (params.situacao) sp.set('situacao', params.situacao);
  const q = sp.toString();
  return request<ParliamentarianOut[]>(`/parliamentarians/${q ? `?${q}` : ''}`);
}

export function getParliamentarian(id: number): Promise<ParliamentarianDetailOut> {
  return request<ParliamentarianDetailOut>(`/parliamentarians/${id}`);
}

export type PropositionSortBy =
  | 'created_at'
  | 'updated_at'
  | 'title'
  | 'presentation_date'
  | 'presentation_year'
  | 'proposition_number';

export type SortOrder = 'asc' | 'desc';

export interface ListPropositionsParams {
  limit?: number;
  offset?: number;
  year?: number;
  acronym?: string;
  presentation_date_from?: string;
  presentation_date_to?: string;
  created_from?: string;
  created_to?: string;
  updated_from?: string;
  updated_to?: string;
  sort_by?: PropositionSortBy;
  sort_order?: SortOrder;
}

export function listPropositions(
  params: ListPropositionsParams = {}
): Promise<PropositionOut[]> {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', String(params.limit));
  if (params.offset != null) sp.set('offset', String(params.offset));
  if (params.year != null) sp.set('year', String(params.year));
  if (params.acronym) sp.set('acronym', params.acronym);
  if (params.presentation_date_from) sp.set('presentation_date_from', params.presentation_date_from);
  if (params.presentation_date_to) sp.set('presentation_date_to', params.presentation_date_to);
  if (params.created_from) sp.set('created_from', params.created_from);
  if (params.created_to) sp.set('created_to', params.created_to);
  if (params.updated_from) sp.set('updated_from', params.updated_from);
  if (params.updated_to) sp.set('updated_to', params.updated_to);
  if (params.sort_by) sp.set('sort_by', params.sort_by);
  if (params.sort_order) sp.set('sort_order', params.sort_order);
  const q = sp.toString();
  return request<PropositionOut[]>(`/propositions/${q ? `?${q}` : ''}`);
}

export function getProposition(id: number): Promise<PropositionOut> {
  return request<PropositionOut>(`/propositions/${id}`);
}

export interface ListPropositionsByParliamentarianParams {
  limit?: number;
  year?: number;
  acronym?: string;
  presentation_date_from?: string;
  presentation_date_to?: string;
  created_from?: string;
  created_to?: string;
  updated_from?: string;
  updated_to?: string;
  sort_by?: PropositionSortBy;
  sort_order?: SortOrder;
}

const AUTHORSHIP_SORT_KEYS = new Set<PropositionSortBy>(['created_at', 'updated_at']);

/** Fetches propositions for which the given parliamentarian is an author (via authors-proposition). */
export async function listPropositionsByParliamentarian(
  parliamentarianId: number,
  params: ListPropositionsByParliamentarianParams = {}
): Promise<PropositionOut[]> {
  const limit = params.limit ?? 500;
  const sortByForAuthorship: AuthorsPropositionSortBy | undefined =
    params.sort_by != null && AUTHORSHIP_SORT_KEYS.has(params.sort_by)
      ? (params.sort_by as AuthorsPropositionSortBy)
      : undefined;

  const authorships = await listAuthorsPropositions({
    parliamentarian_id: parliamentarianId,
    limit,
    offset: 0,
    created_from: params.created_from,
    created_to: params.created_to,
    updated_from: params.updated_from,
    updated_to: params.updated_to,
    sort_by: sortByForAuthorship,
    sort_order: params.sort_order,
  });
  const propositionIds = [...new Set(authorships.map((a) => a.proposition_id))];
  const propositions = await Promise.all(propositionIds.map((id) => getProposition(id)));

  const filtered = propositions.filter((p) => {
    if (params.year != null && p.presentation_year !== params.year) return false;
    if (params.acronym) {
      const needle = params.acronym.toLowerCase();
      const hay = (p.proposition_acronym ?? '').toLowerCase();
      if (!hay.includes(needle)) return false;
    }
    if (params.presentation_date_from) {
      if (!p.presentation_date) return false;
      if (String(p.presentation_date) < params.presentation_date_from) return false;
    }
    if (params.presentation_date_to) {
      if (!p.presentation_date) return false;
      if (String(p.presentation_date) > params.presentation_date_to) return false;
    }
    return true;
  });

  if (params.sort_by) {
    const dir = params.sort_order === 'asc' ? 1 : -1;
    const key = params.sort_by;
    filtered.sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[key];
      const bv = (b as unknown as Record<string, unknown>)[key];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
  }

  return filtered;
}

export type RollCallVoteSortBy =
  | 'created_at'
  | 'updated_at'
  | 'id'
  | 'parliamentarian_id'
  | 'proposition_id';

export interface ListRollCallVotesParams {
  limit?: number;
  offset?: number;
  parliamentarian_id?: number;
  proposition_id?: number;
  created_from?: string;
  created_to?: string;
  updated_from?: string;
  updated_to?: string;
  sort_by?: RollCallVoteSortBy;
  sort_order?: SortOrder;
}

export function listRollCallVotes(
  params: ListRollCallVotesParams = {}
): Promise<RollCallVoteOut[]> {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', String(params.limit));
  if (params.offset != null) sp.set('offset', String(params.offset));
  if (params.parliamentarian_id != null)
    sp.set('parliamentarian_id', String(params.parliamentarian_id));
  if (params.proposition_id != null)
    sp.set('proposition_id', String(params.proposition_id));
  if (params.created_from) sp.set('created_from', params.created_from);
  if (params.created_to) sp.set('created_to', params.created_to);
  if (params.updated_from) sp.set('updated_from', params.updated_from);
  if (params.updated_to) sp.set('updated_to', params.updated_to);
  if (params.sort_by) sp.set('sort_by', params.sort_by);
  if (params.sort_order) sp.set('sort_order', params.sort_order);
  const q = sp.toString();
  return request<RollCallVoteOut[]>(`/roll-call-votes/${q ? `?${q}` : ''}`);
}

export function getRollCallVote(id: number): Promise<RollCallVoteOut> {
  return request<RollCallVoteOut>(`/roll-call-votes/${id}`);
}

export type SpeechesTranscriptSortBy =
  | 'created_at'
  | 'updated_at'
  | 'date'
  | 'id'
  | 'parliamentarian_id';

export interface ListSpeechesTranscriptsParams {
  limit?: number;
  offset?: number;
  parliamentarian_id?: number;
  date_from?: string;
  date_to?: string;
  created_from?: string;
  created_to?: string;
  updated_from?: string;
  updated_to?: string;
  sort_by?: SpeechesTranscriptSortBy;
  sort_order?: SortOrder;
}

export function listSpeechesTranscripts(
  params: ListSpeechesTranscriptsParams = {}
): Promise<SpeechesTranscriptOut[]> {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', String(params.limit));
  if (params.offset != null) sp.set('offset', String(params.offset));
  if (params.parliamentarian_id != null)
    sp.set('parliamentarian_id', String(params.parliamentarian_id));
  if (params.date_from) sp.set('date_from', params.date_from);
  if (params.date_to) sp.set('date_to', params.date_to);
  if (params.created_from) sp.set('created_from', params.created_from);
  if (params.created_to) sp.set('created_to', params.created_to);
  if (params.updated_from) sp.set('updated_from', params.updated_from);
  if (params.updated_to) sp.set('updated_to', params.updated_to);
  if (params.sort_by) sp.set('sort_by', params.sort_by);
  if (params.sort_order) sp.set('sort_order', params.sort_order);
  const q = sp.toString();
  return request<SpeechesTranscriptOut[]>(`/speeches-transcripts/${q ? `?${q}` : ''}`);
}

export function getSpeechesTranscript(id: number): Promise<SpeechesTranscriptOut> {
  return request<SpeechesTranscriptOut>(`/speeches-transcripts/${id}`);
}

export function getSpeechAnalysis(speechId: number): Promise<SpeechAnalysisOut> {
  return request<SpeechAnalysisOut>(`/analysis/${speechId}`);
}

export function listProjectFavorites(
  projectId: number,
  params: { limit?: number; offset?: number } = {}
): Promise<ProjectFavoriteOut[]> {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', String(params.limit));
  if (params.offset != null) sp.set('offset', String(params.offset));
  const q = sp.toString();
  return request<ProjectFavoriteOut[]>(
    `/projects/${projectId}/favorites${q ? `?${q}` : ''}`
  );
}

export function listMyProjectFavorites(
  params: { limit?: number; offset?: number } = {}
): Promise<ProjectFavoriteOut[]> {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', String(params.limit));
  if (params.offset != null) sp.set('offset', String(params.offset));
  const q = sp.toString();
  return request<ProjectFavoriteOut[]>(`/projects/me/favorites${q ? `?${q}` : ''}`);
}

export function addMyProjectFavorite(parliamentarianId: number): Promise<ProjectFavoriteOut> {
  return request<ProjectFavoriteOut>('/projects/me/favorites', {
    method: 'POST',
    body: JSON.stringify({ parliamentarian_id: parliamentarianId }),
  });
}

export function removeMyProjectFavorite(parliamentarianId: number): Promise<void> {
  return request<void>(`/projects/me/favorites/${parliamentarianId}`, {
    method: 'DELETE',
  });
}

/** Estatísticas dos últimos 3 meses para parlamentares favoritados no projeto autenticado. */
export function getMyDashboardStats(): Promise<DashboardStatsOut> {
  return request<DashboardStatsOut>('/projects/me/dashboard-stats');
}

/** Atividades recentes para parlamentares favoritados no projeto autenticado. */
export function getMyDashboardActivity(params: { limit?: number } = {}): Promise<DashboardActivityOut> {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', String(params.limit));
  const q = sp.toString();
  return request<DashboardActivityOut>(`/projects/me/dashboard-activity${q ? `?${q}` : ''}`);
}

export type AuthorsPropositionSortBy =
  | 'created_at'
  | 'updated_at'
  | 'id'
  | 'parliamentarian_id'
  | 'proposition_id';

export interface ListAuthorsPropositionParams {
  limit?: number;
  offset?: number;
  parliamentarian_id?: number;
  proposition_id?: number;
  created_from?: string;
  created_to?: string;
  updated_from?: string;
  updated_to?: string;
  sort_by?: AuthorsPropositionSortBy;
  sort_order?: SortOrder;
}

export function listAuthorsPropositions(
  params: ListAuthorsPropositionParams = {}
): Promise<AuthorsPropositionOut[]> {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', String(params.limit));
  if (params.offset != null) sp.set('offset', String(params.offset));
  if (params.parliamentarian_id != null)
    sp.set('parliamentarian_id', String(params.parliamentarian_id));
  if (params.proposition_id != null)
    sp.set('proposition_id', String(params.proposition_id));
  if (params.created_from) sp.set('created_from', params.created_from);
  if (params.created_to) sp.set('created_to', params.created_to);
  if (params.updated_from) sp.set('updated_from', params.updated_from);
  if (params.updated_to) sp.set('updated_to', params.updated_to);
  if (params.sort_by) sp.set('sort_by', params.sort_by);
  if (params.sort_order) sp.set('sort_order', params.sort_order);
  const q = sp.toString();
  return request<AuthorsPropositionOut[]>(`/authors-proposition/${q ? `?${q}` : ''}`);
}

export interface ListParliamentarianSpeechAnalysisParams {
  analysis_type?: 'spacy' | 'chatgpt';
  page?: number;
  page_size?: number;
}

export function listParliamentarianSpeechAnalysis(
  parliamentarianCode: number,
  params: ListParliamentarianSpeechAnalysisParams = {}
): Promise<SpeechAnalysisSummaryOut[]> {
  const sp = new URLSearchParams();
  if (params.analysis_type) sp.set('analysis_type', params.analysis_type);
  // if (params.page != null) sp.set('page', String(params.page));
  // if (params.page_size != null) sp.set('page_size', String(params.page_size));
  const q = sp.toString();
  return request<SpeechAnalysisSummaryOut[]>(
    `/analysis/parliamentarian/${parliamentarianCode}${q ? `?${q}` : ''}`
  );
}
