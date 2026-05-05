import { useCallback, useMemo, useState, type ReactNode } from "react";
import { AccountModal } from "./AccountModal";
import { AccountModalContext } from "./accountModalContext";

export function AccountModalProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [launchKey, setLaunchKey] = useState(0);

  const openAccount = useCallback(() => {
    setLaunchKey((k) => k + 1);
    setOpen(true);
  }, []);

  const close = useCallback(() => {
    setOpen(false);
  }, []);

  const value = useMemo(
    () => ({
      openAccount,
      close,
    }),
    [openAccount, close]
  );

  return (
    <AccountModalContext.Provider value={value}>
      {children}
      <AccountModal open={open} onOpenChange={setOpen} launchKey={launchKey} />
    </AccountModalContext.Provider>
  );
}
