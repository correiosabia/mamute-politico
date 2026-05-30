import axios from "axios";
import {
  GHOST_VERSION,
  INTEGRITY_TOKEN_ENDPOINT,
  MAGIC_LINK_ENDPOINT,
} from "./config";

const membersApiHeaders = {
  "app-pragma": "no-cache",
  "x-ghost-version": GHOST_VERSION,
} as const;

function parseIntegrityTokenBody(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed.startsWith("{")) {
    try {
      const parsed = JSON.parse(trimmed) as Record<string, unknown>;
      const token =
        (typeof parsed.integrityToken === "string" && parsed.integrityToken) ||
        (typeof parsed.token === "string" && parsed.token);
      if (token) {
        return token;
      }
    } catch {
      /* fall through */
    }
  }
  return trimmed;
}

/**
 * Fetches a short-lived integrity token required before POST send-magic-link.
 * Ghost must allow CORS with credentials from this app's origin (same as session endpoint).
 */
export async function getIntegrityToken(): Promise<string> {
  const res = await axios.get<string>(INTEGRITY_TOKEN_ENDPOINT, {
    withCredentials: true,
    responseType: "text",
    headers: { ...membersApiHeaders },
  });
  if (res.status !== 200 || typeof res.data !== "string") {
    throw new Error("Resposta do token de integridade inválida");
  }
  const token = parseIntegrityTokenBody(res.data);
  if (!token) {
    throw new Error("Token de integridade vazio");
  }
  return token;
}

export type MagicLinkEmailType = "signin" | "signup";

export type SendMagicLinkParams = {
  email: string;
  emailType: MagicLinkEmailType;
  name?: string;
};

/**
 * Asks Ghost to email a magic link for sign-in or sign-up.
 */
export async function sendMagicLink(params: SendMagicLinkParams): Promise<void> {
  const integrityToken = await getIntegrityToken();
  const body: Record<string, string> = {
    email: params.email.trim(),
    emailType: params.emailType,
    integrityToken,
  };
  if (params.name?.trim()) {
    body.name = params.name.trim();
  }

  const res = await axios.post(MAGIC_LINK_ENDPOINT, body, {
    withCredentials: true,
    headers: {
      "Content-Type": "application/json",
      ...membersApiHeaders,
    },
    validateStatus: () => true,
  });

  if (res.status === 201 || res.status === 200) {
    return;
  }

  const err = new Error("Falha ao enviar link de acesso") as Error & {
    status?: number;
    ghostMessage?: string;
  };
  err.status = res.status;
  const data = res.data as { errors?: Array<{ message?: string }> } | undefined;
  const msg = data?.errors?.[0]?.message;
  if (msg) {
    err.ghostMessage = msg;
    err.message = msg;
  }
  throw err;
}

export function isMemberNotFoundError(error: unknown): boolean {
  const msg =
    (error as { ghostMessage?: string })?.ghostMessage ??
    (error as Error)?.message ??
    "";
  return (
    /member not found/i.test(msg) ||
    /no member exists/i.test(msg) ||
    /no member found/i.test(msg) ||
    /membro n[aã]o encontrado/i.test(msg) ||
    /n[aã]o existe.*membro/i.test(msg) ||
    /please sign up first/i.test(msg) ||
    /sign up first/i.test(msg)
  );
}

export type SendMagicLinkUnifiedResult = {
  emailType: MagicLinkEmailType;
};

/**
 * Sends a magic link for sign-in, or sign-up if no member exists for the email.
 */
export async function sendMagicLinkUnified(params: {
  email: string;
}): Promise<SendMagicLinkUnifiedResult> {
  const email = params.email.trim();
  try {
    await sendMagicLink({ email, emailType: "signin" });
    return { emailType: "signin" };
  } catch (e) {
    if (!isMemberNotFoundError(e)) {
      throw e;
    }
    await sendMagicLink({ email, emailType: "signup" });
    return { emailType: "signup" };
  }
}
