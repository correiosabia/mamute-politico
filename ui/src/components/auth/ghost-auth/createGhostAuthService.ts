import { ensureTokenIsValidOrRedirect } from "./ensureTokenIsValidOrRedirect";
import { notifySubscribers } from "./notifySubscribers";
import {
  clearScheduledTokenRenewal,
  scheduleTokenRenewal,
} from "./scheduleTokenRenewal";
import { setupStateWrapper } from "./setupStateWrapper";
import type {
  GhostAuthServiceConfig,
  GhostAuthStateWrapper,
} from "./types";
import { verifyLikelyValidJWT } from "./verifyLikelyValidJWT";

export function createGhostAuthService(config: GhostAuthServiceConfig) {
  const stateWrapper: GhostAuthStateWrapper = {
    token: null,
    likelyValidAndParsedToken: null,
    isLoading: false,
    queue: [],
    subscribers: [],
    config: {
      publicKey: null,
      tokenEndpoint: null,
      loginURL: null,
      storageKey: null,
      persistenceChoice: null,
    },
  };

  setupStateWrapper(stateWrapper, config);
  ensureTokenIsValidOrRedirect(stateWrapper);

  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        scheduleTokenRenewal(stateWrapper);
      }
    });
  }

  return {
    subscribe(fn: () => void) {
      if (!stateWrapper.subscribers.includes(fn)) {
        stateWrapper.subscribers.push(fn);
      }
      return () => {
        stateWrapper.subscribers = stateWrapper.subscribers.filter((f) => f !== fn);
      };
    },
    getSnapshot(): string | null {
      if (verifyLikelyValidJWT(stateWrapper)) {
        return stateWrapper.token;
      }
      return null;
    },
    signOut() {
      clearScheduledTokenRenewal();
      stateWrapper.token = null;
      stateWrapper.likelyValidAndParsedToken = null;
      stateWrapper.isLoading = false;
      stateWrapper.queue = [];
      if (
        stateWrapper.config.storageKey &&
        stateWrapper.config.persistenceChoice
      ) {
        stateWrapper.config.persistenceChoice.removeItem(
          stateWrapper.config.storageKey
        );
      }
      notifySubscribers(stateWrapper);
    },
  };
}
