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
  qtd_consultas_ia_mes?: number;
  qtd_email?: number;
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
