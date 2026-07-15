import { publicKey } from "./publicKey";

// Default '' = same-origin: navegador resolve /members/... contra a origem da app.
// Em prod e dev (com Caddy) o reverse proxy roteia /members/* pro Ghost. Override via VITE_BASE_URL
// quando UI e Ghost rodam em hosts diferentes.
export const AUTH_API_ROOT =
  (import.meta.env.VITE_BASE_URL as string | undefined) ?? "";
export const TOKEN_ENDPOINT = `${AUTH_API_ROOT}/members/api/session/`;
export const MEMBER_ENDPOINT = `${AUTH_API_ROOT}/members/api/member/`;
export const MEMBER_EMAIL_ENDPOINT = `${AUTH_API_ROOT}/members/api/member/email`;
export const INTEGRITY_TOKEN_ENDPOINT = `${AUTH_API_ROOT}/members/api/integrity-token/`;
export const MAGIC_LINK_ENDPOINT = `${AUTH_API_ROOT}/members/api/send-magic-link/`;
export const WELL_KNOWN_ENDPOINT = `${AUTH_API_ROOT}/members/.well-known/jwks.json`;

/** Sent as `x-ghost-version` when calling Members API (integrity token, magic link). Override via VITE_GHOST_VERSION if your Ghost build requires a specific value. */
export const GHOST_VERSION =
  (import.meta.env.VITE_GHOST_VERSION as string | undefined) ?? "5.100";

export const JWT_TOKEN_KEY = "mamutePoliticoJwtToken";
export const LOGIN_URL = `${AUTH_API_ROOT}/#/portal/signin`;
export const ACCOUNT_URL = `${AUTH_API_ROOT}/#/portal/account`;
export const PLANS_URL = `${AUTH_API_ROOT}/#/portal/account/plans`;
export const SIGNUP_URL = `${AUTH_API_ROOT}/#/portal/signup`;

const tokenPersistenceChoice =
  typeof window !== "undefined"
    ? localStorage
    : {
        setItem: () => null,
        getItem: () => null,
        removeItem: () => null,
      };

export const ghostClientConfig = {
  publicKey,
  tokenEndpoint: TOKEN_ENDPOINT,
  loginURL: LOGIN_URL,
  persistenceChoice: tokenPersistenceChoice,
  storageKey: JWT_TOKEN_KEY,
};
