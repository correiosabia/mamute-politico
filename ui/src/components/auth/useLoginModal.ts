import { useContext } from "react";
import { LoginModalContext } from "./loginModalContext";
import type { LoginModalContextValue } from "./loginModalContext";

export function useLoginModal(): LoginModalContextValue {
  const ctx = useContext(LoginModalContext);
  if (!ctx) {
    throw new Error("useLoginModal must be used within LoginModalProvider");
  }
  return ctx;
}
