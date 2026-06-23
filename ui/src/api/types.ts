/** API response types matching FastAPI/Pydantic schemas. */

export interface ParliamentarianOut {
  id: number;
  type?: string | null;
  parliamentarian_code?: number | null;
  name?: string | null;
  full_name?: string | null;
  email?: string | null;
  telephone?: string | null;
  cpf?: string | null;
  status?: string | null;
  party?: string | null;
  state_of_birth?: string | null;
  city_of_birth?: string | null;
  state_elected?: string | null;
  site?: string | null;
  education?: string | null;
  office_name?: string | null;
  office_building?: string | null;
  office_number?: string | null;
  office_floor?: string | null;
  office_email?: string | null;
  biography_link?: string | null;
  biography_text?: string | null;
  details?: Record<string, unknown> | null;
  photo_url?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SocialNetworkLinkOut {
  name?: string | null;
  profile_url?: string | null;
}

export interface ParliamentarianDetailOut extends ParliamentarianOut {
  social_networks?: SocialNetworkLinkOut[];
}

export interface PropositionOut {
  id: number;
  proposition_code?: number | null;
  title?: string | null;
  link?: string | null;
  proposition_acronym?: string | null;
  proposition_number?: number | null;
  presentation_year?: number | null;
  agency_id?: number | null;
  proposition_type_id?: number | null;
  proposition_status_id?: number | null;
  current_status?: string | null;
  proposition_description?: string | null;
  presentation_date?: string | null;
  presentation_month?: number | null;
  summary?: string | null;
  details?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface RollCallVoteOut {
  id: number;
  parliamentarian_id: number;
  proposition_id: number;
  proposition_title?: string | null;
  vote?: string | null;
  description?: string | null;
  link?: string | null;
  proposition_votes_link?: string | null;
  date_vote?: string | null;
  created_at: string;
  updated_at: string;
  parliamentarian_name?: string | null;
  parliamentarian_party?: string | null;
  parliamentarian_state_elected?: string | null;
}

export interface SpeechesTranscriptOut {
  id: number;
  parliamentarian_id: number;
  date?: string | null;
  session_number?: string | null;
  type?: string | null;
  speech_link?: string | null;
  speech_text?: string | null;
  summary?: string | null;
  hour_minute?: string | null;
  publication_link?: string | null;
  publication_text?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectFavoriteOut {
  id: number;
  projeto_id: number;
  parliamentarian_id: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectFavoriteQuotaOut {
  limit: number;
  used: number;
  remaining: number;
  limit_reached: boolean;
}

export interface DashboardStatsOut {
  propositions_this_week: number;
  attendance_avg_percent?: number | null;
  recent_votes_count: number;
  speeches_count: number;
}

export interface DashboardActivityAuthorOut {
  id: number;
  name?: string | null;
  full_name?: string | null;
  party?: string | null;
  state_elected?: string | null;
  type?: string | null;
}

export interface DashboardActivityPropositionOut extends PropositionOut {
  monitored_authors: DashboardActivityAuthorOut[];
}

export interface DashboardActivityOut {
  propositions: DashboardActivityPropositionOut[];
  votes: RollCallVoteOut[];
}

export interface AuthorsPropositionOut {
  id: number;
  parliamentarian_id: number;
  proposition_id: number;
  created_at: string;
  updated_at: string;
}

export interface AnalysisKeywordOut {
  id: number;
  keyword: string;
  term: string;
  frequency: number;
  rank: number;
  is_primary: boolean;
  analysis_type: string;
}

export interface SpeechAnalysisSummaryOut {
  id: number;
  date?: string | null;
  analysis_types: string[];
  primary_keyword?: AnalysisKeywordOut | null;
  keywords_count: number;
  entities_count: number;
}

export interface AnalysisEntityOut {
  id: number;
  label: string;
  text: string;
  start_char: number;
  end_char: number;
  analysis_type: string;
}

export interface SpeechAnalysisOut {
  speech_id: number;
  keywords: AnalysisKeywordOut[];
  entities: AnalysisEntityOut[];
}
