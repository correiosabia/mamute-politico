import { useContext } from "react";
import {
  AccountModalContext,
  type AccountModalContextValue,
} from "./accountModalContext";

export function useAccountModal(): AccountModalContextValue {
  const ctx = useContext(AccountModalContext);
  if (!ctx) {
    throw new Error("useAccountModal must be used within AccountModalProvider");
  }
  return ctx;
}
