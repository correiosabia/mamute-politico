import { request } from './client';

export interface WhoamiResponse {
  email: string;
  is_admin: boolean;
}

/** Confirma no backend se o membro logado é admin. 404 = não admin. */
export function fetchWhoami(): Promise<WhoamiResponse> {
  return request<WhoamiResponse>('/admin/whoami');
}

export interface TierDetails {
  qtd_termos?: number;
  qtd_termos_camara?: number;
  qtd_termos_senado?: number;
  qtd_consultas_ia_mes?: number;
  qtd_consultas_ia_semana?: number;
  periodicidade_email?: string[];
  orgao?: string[];
  preco_mensal?: number;
  [key: string]: unknown;
}

export interface Tier {
  id: number;
  tier_name_debug: string;
  product_id: string;
  detalhes: TierDetails;
}

export function fetchTiers(): Promise<Tier[]> {
  return request<Tier[]>('/admin/tiers');
}

export function updateTier(id: number, patch: TierDetails): Promise<Tier> {
  return request<Tier>(`/admin/tiers/${id}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export interface MetricsOverview {
  usuarios: number;
  consultas_mes: number;
  tokens_mes: number;
  custo_mes: number;
  custo_mes_brl: number;
  receita_mes: number;
  margem_mes: number;
  usd_brl_rate: number;
  parlamentares_monitorados: number;
  usuarios_acima_do_plano: number;
}

export interface MetricsUser {
  projeto_id: number;
  email: string;
  nome: string;
  plano: string | null;
  preco_mensal: number;
  consultas_mes: number;
  consultas_total: number;
  tokens_mes: number;
  custo_mes: number;
  custo_mes_brl: number;
  margem_mes: number;
  parlamentares_monitorados: number;
  limite_parlamentares: number | null;
  limite_consultas: number | null;
  acima_do_plano: boolean;
}

export interface MetricsUsersResponse {
  period_start: string;
  usd_brl_rate: number;
  users: MetricsUser[];
}

export function fetchMetricsOverview(): Promise<MetricsOverview> {
  return request<MetricsOverview>('/admin/metrics/overview');
}

export function fetchMetricsUsers(params?: {
  limit?: number;
  search?: string;
}): Promise<MetricsUsersResponse> {
  const qs = new URLSearchParams();
  if (params?.limit != null) qs.set('limit', String(params.limit));
  if (params?.search) qs.set('search', params.search);
  return request<MetricsUsersResponse>(`/admin/metrics/users?${qs.toString()}`);
}

export interface ToolUsage {
  tool: string;
  uses: number;
}

export function fetchTools(): Promise<{ tools: ToolUsage[] }> {
  return request<{ tools: ToolUsage[] }>('/admin/metrics/tools');
}

export interface SectionUsage {
  page: string;
  section: string;
  views: number;
}

export function fetchSections(): Promise<{ sections: SectionUsage[] }> {
  return request<{ sections: SectionUsage[] }>('/admin/metrics/sections');
}

export interface MonitoredParliamentarian {
  parliamentarian_id: number;
  name: string;
  house: 'camara' | 'senado';
  state: string;
  monitors: number;
}

export interface ParliamentariansMetrics {
  top: MonitoredParliamentarian[];
  by_house: { camara: number; senado: number };
  by_state: { state: string; monitors: number }[];
}

export function fetchParliamentarians(): Promise<ParliamentariansMetrics> {
  return request<ParliamentariansMetrics>('/admin/metrics/parliamentarians');
}

export interface IaMetrics {
  consultas_mes: number;
  tokens_mes: number;
  custo_mes_brl: number;
  usd_brl_rate: number;
  por_dia: { dia: string; consultas: number; custo_brl: number }[];
  top_usuarios: {
    projeto_id: number;
    email: string;
    nome: string;
    consultas_mes: number;
    custo_mes_brl: number;
  }[];
}

export function fetchIa(): Promise<IaMetrics> {
  return request<IaMetrics>('/admin/metrics/ia');
}

export type EmailSendStatus =
  | 'sent'
  | 'error'
  | 'skipped_no_favorites'
  | 'skipped_no_activity';

export interface EmailLogEntry {
  id: number;
  projeto_id: number;
  email: string;
  periodicidade: string;
  periodicidade_label: string;
  status: EmailSendStatus;
  detail: string | null;
  subject: string | null;
  stats: Record<string, number> | null;
  period_start: string | null;
  period_end: string | null;
  created_at: string | null;
}

export interface EmailUpcoming {
  periodicidade: string;
  periodicidade_label: string;
  proximo_envio: string | null;
  tiers: string[];
  destinatarios: number;
  com_favoritos: number;
}

export interface EmailsMetrics {
  log_disponivel: boolean;
  kpis: {
    enviados: number;
    erros: number;
    pulados: number;
    ultimo_envio: string | null;
  };
  historico: EmailLogEntry[];
  proximos: EmailUpcoming[];
}

export function fetchEmails(): Promise<EmailsMetrics> {
  return request<EmailsMetrics>('/admin/metrics/emails');
}

export type CoverageStatus =
  | 'completo'
  | 'quase'
  | 'parcial'
  | 'superset'
  | 'sem_referencia'
  | 'ausente';

interface YearNosso {
  year: number;
  nosso: number;
}

interface CasaBlocks {
  camara: YearNosso[];
  senado: YearNosso[];
  nota: string;
}

export interface Coverage {
  /** true = rotina ainda não computou o snapshot (deploy novo). */
  pending?: boolean;
  /** ISO do último cálculo (rotina diária 04h). */
  computed_at?: string | null;
  kpis: {
    proposicoes: number;
    discursos: number;
    votacoes_nominais: number;
    parlamentares: number;
  };
  proposicoes: {
    camara: {
      year: number;
      nosso: number;
      oficial: number | null;
      pct: number | null;
      status: CoverageStatus;
    }[];
    senado: YearNosso[];
    sem_tipo_total?: number;
    nota_superset: string;
  };
  discursos: CasaBlocks;
  votacoes: CasaBlocks;
  parlamentares: {
    deputados: { nossa_base: number; cadeiras: number; status: CoverageStatus };
    senadores: { nossa_base: number; cadeiras: number; status: CoverageStatus };
    nota: string;
  };
  consolidado: { categoria: string; status: CoverageStatus; observacao: string }[];
}

export function fetchCoverage(): Promise<Coverage> {
  return request<Coverage>('/admin/coverage');
}

export interface UserDetail extends MetricsUser {
  ia_por_dia: { dia: string; consultas: number; custo_brl: number }[];
  paginas: { page: string; views: number }[];
  trocas: { adicionados: number; removidos: number; total: number };
}

export function fetchUserDetail(id: number): Promise<UserDetail> {
  return request<UserDetail>(`/admin/metrics/users/${id}`);
}
