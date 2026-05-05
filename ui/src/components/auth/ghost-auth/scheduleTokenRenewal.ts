import { ensureTokenIsValidOrRedirect } from "./ensureTokenIsValidOrRedirect";
import { getJWTExpirationCountdown } from "./getJWTExpirationCountdown";
import { renewToken } from "./renewToken";
import type { GhostAuthStateWrapper } from "./types";

let nextRenew: ReturnType<typeof setTimeout> | undefined;

export function clearScheduledTokenRenewal(): void {
  if (nextRenew !== undefined) {
    clearTimeout(nextRenew);
    nextRenew = undefined;
  }
}

export async function scheduleTokenRenewal(
  stateWrapper: GhostAuthStateWrapper
): Promise<void> {
  if (!stateWrapper.likelyValidAndParsedToken) {
    await ensureTokenIsValidOrRedirect(stateWrapper);
    return;
  }
  try {
    const expirationCountdown = getJWTExpirationCountdown(
      stateWrapper.likelyValidAndParsedToken
    );
    const nextTime = Math.max(500, expirationCountdown - 60 * 1000);
    if (nextRenew) clearTimeout(nextRenew);
    nextRenew = setTimeout(async () => {
      await renewToken(stateWrapper);
      scheduleTokenRenewal(stateWrapper);
    }, nextTime);
  } catch {
    await renewToken(stateWrapper);
  }
}
