import axios from "axios";
import {
  GHOST_VERSION,
  MEMBER_EMAIL_ENDPOINT,
  MEMBER_ENDPOINT,
  TOKEN_ENDPOINT,
} from "./config";

const membersApiHeaders = {
  "app-pragma": "no-cache",
  "x-ghost-version": GHOST_VERSION,
} as const;

export type CurrentMember = {
  name: string | null;
  email: string;
  uuid: string;
  status?: string;
  subscribed?: boolean;
  comped?: boolean;
  newsletters?: MemberNewsletter[];
  tiers?: MemberTier[];
  subscriptions?: MemberSubscription[];
};

export type MemberNewsletter = {
  id: string;
  name?: string;
};

export type MemberTier = {
  id?: string;
  name?: string;
  slug?: string;
};

export type MemberSubscription = {
  id?: string;
  status?: string;
  tier?: MemberTier;
  price?: {
    amount?: number;
    currency?: string;
    interval?: string;
  };
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseNewsletter(value: unknown): MemberNewsletter | null {
  if (!isRecord(value) || typeof value.id !== "string") return null;
  return {
    id: value.id,
    ...(typeof value.name === "string" ? { name: value.name } : {}),
  };
}

function parseTier(value: unknown): MemberTier | null {
  if (!isRecord(value)) return null;
  const tier: MemberTier = {};
  if (typeof value.id === "string") tier.id = value.id;
  if (typeof value.name === "string") tier.name = value.name;
  if (typeof value.slug === "string") tier.slug = value.slug;
  return Object.keys(tier).length > 0 ? tier : null;
}

function parseSubscription(value: unknown): MemberSubscription | null {
  if (!isRecord(value)) return null;
  const subscription: MemberSubscription = {};
  if (typeof value.id === "string") subscription.id = value.id;
  if (typeof value.status === "string") subscription.status = value.status;

  const tier = parseTier(value.tier);
  if (tier) subscription.tier = tier;

  if (isRecord(value.price)) {
    const price: NonNullable<MemberSubscription["price"]> = {};
    if (typeof value.price.amount === "number") price.amount = value.price.amount;
    if (typeof value.price.currency === "string") price.currency = value.price.currency;
    if (typeof value.price.interval === "string") price.interval = value.price.interval;
    if (Object.keys(price).length > 0) subscription.price = price;
  }

  return Object.keys(subscription).length > 0 ? subscription : null;
}

function parseArray<T>(
  value: unknown,
  parser: (item: unknown) => T | null
): T[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.map(parser).filter((item): item is T => item !== null);
}

/**
 * Returns the signed-in Ghost member, or null if no session (204 / empty).
 */
export async function fetchCurrentMember(
  signal?: AbortSignal
): Promise<CurrentMember | null> {
  const res = await axios.get<unknown>(MEMBER_ENDPOINT, {
    withCredentials: true,
    headers: { ...membersApiHeaders },
    signal,
    validateStatus: (status) =>
      status === 200 || status === 204 || status === 401,
  });

  if (res.status === 204 || res.status === 401) {
    return null;
  }

  try {
    return parseMemberPayload(res.data);
  } catch {
    return null;
  }
}

function parseMemberPayload(data: unknown): CurrentMember {
  if (!isRecord(data)) {
    throw new Error("Resposta inválida do servidor");
  }

  const email = typeof data.email === "string" ? data.email : "";
  const uuid = typeof data.uuid === "string" ? data.uuid : "";
  if (!email || !uuid) {
    throw new Error("Resposta inválida do servidor");
  }

  const name =
    typeof data.name === "string" && data.name.trim() !== ""
      ? data.name
      : null;

  const status = typeof data.status === "string" ? data.status : undefined;

  const subscribed =
    typeof data.subscribed === "boolean" ? data.subscribed : undefined;
  const comped = typeof data.comped === "boolean" ? data.comped : undefined;
  const newsletters = parseArray(data.newsletters, parseNewsletter);
  const tiers = parseArray(data.tiers, parseTier);
  const subscriptions = parseArray(data.subscriptions, parseSubscription);

  return {
    name,
    email,
    uuid,
    status,
    ...(subscribed !== undefined ? { subscribed } : {}),
    ...(comped !== undefined ? { comped } : {}),
    ...(newsletters !== undefined ? { newsletters } : {}),
    ...(tiers !== undefined ? { tiers } : {}),
    ...(subscriptions !== undefined ? { subscriptions } : {}),
  };
}

function ghostErrorMessage(data: unknown, fallback: string): string {
  if (!isRecord(data)) {
    return fallback;
  }
  const errors = data.errors;
  if (Array.isArray(errors) && errors.length > 0) {
    const first = errors[0];
    if (isRecord(first) && typeof first.message === "string") {
      return first.message;
    }
  }
  return fallback;
}

/**
 * Returns the session identity token required for sensitive member actions (e.g. email change).
 */
export async function fetchIdentityToken(): Promise<string> {
  const res = await axios.get<string>(TOKEN_ENDPOINT, {
    withCredentials: true,
    responseType: "text",
    headers: { ...membersApiHeaders },
    validateStatus: () => true,
  });

  if (res.status === 200 && typeof res.data === "string" && res.data.trim()) {
    return res.data.trim();
  }

  const err = new Error("Não foi possível obter token de sessão");
  (err as Error & { status?: number }).status = res.status;
  throw err;
}

/**
 * Updates the signed-in member's display name.
 */
export async function updateMemberProfile(params: {
  name: string | null;
}): Promise<CurrentMember> {
  const name =
    params.name === null || params.name.trim() === ""
      ? null
      : params.name.trim();

  const res = await axios.put<unknown>(
    MEMBER_ENDPOINT,
    { name },
    {
      withCredentials: true,
      headers: {
        "Content-Type": "application/json",
        ...membersApiHeaders,
      },
      validateStatus: () => true,
    }
  );

  if (res.status === 200) {
    return parseMemberPayload(res.data);
  }

  const err = new Error(
    ghostErrorMessage(res.data, "Não foi possível atualizar seu perfil")
  ) as Error & { status?: number; ghostMessage?: string };
  err.status = res.status;
  err.ghostMessage = err.message;
  throw err;
}

/**
 * Subscribes or unsubscribes the signed-in member from the site's default newsletter.
 * Mamute currently exposes one newsletter, matching Ghost Portal's single-newsletter toggle.
 */
export async function updateMemberNewsletterSubscription(params: {
  subscribed: boolean;
}): Promise<CurrentMember> {
  const res = await axios.put<unknown>(
    MEMBER_ENDPOINT,
    { subscribed: params.subscribed },
    {
      withCredentials: true,
      headers: {
        "Content-Type": "application/json",
        ...membersApiHeaders,
      },
      validateStatus: () => true,
    }
  );

  if (res.status === 200) {
    return parseMemberPayload(res.data);
  }

  const err = new Error(
    ghostErrorMessage(
      res.data,
      "Não foi possível atualizar a assinatura da newsletter"
    )
  ) as Error & { status?: number; ghostMessage?: string };
  err.status = res.status;
  err.ghostMessage = err.message;
  throw err;
}

/**
 * Sends a confirmation link to the new email address. The account email changes only after the link is clicked.
 */
export async function requestMemberEmailChange(params: {
  email: string;
}): Promise<void> {
  const identity = await fetchIdentityToken();
  const email = params.email.trim();

  const res = await axios.post(
    MEMBER_EMAIL_ENDPOINT,
    { identity, email },
    {
      withCredentials: true,
      headers: {
        "Content-Type": "application/json",
        ...membersApiHeaders,
      },
      validateStatus: () => true,
    }
  );

  if (res.status === 201 || res.status === 200) {
    return;
  }

  const err = new Error(
    ghostErrorMessage(res.data, "Não foi possível solicitar alteração de e-mail")
  ) as Error & { status?: number; ghostMessage?: string };
  err.status = res.status;
  err.ghostMessage = err.message;
  throw err;
}

/**
 * Invalidates the Ghost member session cookie (this device only).
 */
export async function signOut(): Promise<void> {
  const res = await axios.delete(TOKEN_ENDPOINT, {
    withCredentials: true,
    headers: { ...membersApiHeaders },
    validateStatus: () => true,
  });

  if (res.status === 204 || res.status === 200) {
    return;
  }

  const err = new Error("Não foi possível encerrar a sessão no servidor");
  (err as Error & { status?: number }).status = res.status;
  throw err;
}

/**
 * Deletes the currently authenticated Ghost member account.
 */
export async function deleteMyAccount(): Promise<void> {
  const res = await axios.delete(MEMBER_ENDPOINT, {
    withCredentials: true,
    headers: { ...membersApiHeaders },
    validateStatus: () => true,
  });

  if (res.status === 204 || res.status === 200 || res.status === 202) {
    return;
  }

  const err = new Error("Não foi possível excluir sua conta");
  (err as Error & { status?: number }).status = res.status;
  throw err;
}

export function isDeleteAccountNotSupportedError(error: unknown): boolean {
  return (error as { status?: number })?.status === 404;
}
