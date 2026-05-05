import type { GhostAuthStateWrapper } from "./types";

export function notifySubscribers(stateWrapper: GhostAuthStateWrapper) {
  for (const subscriber of stateWrapper.subscribers) {
    subscriber();
  }
}
