import { useCallback, useMemo, useState, type ReactNode } from "react";
import { LoginModal } from "./LoginModal";
import { LoginModalContext } from "./loginModalContext";
import type { OpenLoginOptions } from "./loginModalContext";

export type { OpenLoginOptions } from "./loginModalContext";

export function LoginModalProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [launchKey, setLaunchKey] = useState(0);
  const [initialTab, setInitialTab] = useState<"signin" | "signup">("signin");
  const [initialEmail, setInitialEmail] = useState("");

  const openLogin = useCallback((options?: OpenLoginOptions) => {
    setInitialTab(options?.defaultTab ?? "signin");
    setInitialEmail(options?.defaultEmail ?? "");
    setLaunchKey((k) => k + 1);
    setOpen(true);
  }, []);

  const openSignup = useCallback(() => {
    openLogin({ defaultTab: "signup" });
  }, [openLogin]);

  const close = useCallback(() => {
    setOpen(false);
  }, []);

  const value = useMemo(
    () => ({
      openLogin,
      openSignup,
      close,
    }),
    [openLogin, openSignup, close]
  );

  return (
    <LoginModalContext.Provider value={value}>
      {children}
      <LoginModal
        open={open}
        onOpenChange={setOpen}
        launchKey={launchKey}
        initialTab={initialTab}
        initialEmail={initialEmail}
      />
    </LoginModalContext.Provider>
  );
}
