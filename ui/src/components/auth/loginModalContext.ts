import { createContext } from "react";

export type OpenLoginOptions = {
  defaultTab?: "signin" | "signup";
  defaultEmail?: string;
};

export type LoginModalContextValue = {
  openLogin: (options?: OpenLoginOptions) => void;
  openSignup: () => void;
  /** Alias for closing the login dialog. */
  close: () => void;
};

export const LoginModalContext = createContext<LoginModalContextValue | null>(
  null
);
