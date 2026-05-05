import { createContext } from "react";

export type AccountModalContextValue = {
  openAccount: () => void;
  close: () => void;
};

export const AccountModalContext = createContext<AccountModalContextValue | null>(
  null
);
