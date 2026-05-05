import { useSyncExternalStore } from "react";
import { createGhostAuthService } from "../createGhostAuthService";
import { ghostClientConfig } from "../../config";

const ghostService = createGhostAuthService(ghostClientConfig);

export function useGhostAuth(): string | null {
  return useSyncExternalStore(
    ghostService.subscribe,
    ghostService.getSnapshot,
    ghostService.getSnapshot
  );
}

/** Clears the cached JWT and in-memory auth state so the UI updates without a full reload. */
export function ghostSignOut(): void {
  ghostService.signOut();
}
