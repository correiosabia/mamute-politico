import { request } from './client';

export interface WhoamiResponse {
  email: string;
  is_admin: boolean;
}

/** Confirma no backend se o membro logado é admin. 404 = não admin. */
export function fetchWhoami(): Promise<WhoamiResponse> {
  return request<WhoamiResponse>('/admin/whoami');
}
