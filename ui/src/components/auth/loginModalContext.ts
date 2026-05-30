import { createContext } from "react";

export type OpenLoginOptions = {
  defaultEmail?: string;
};

export type LoginModalContextValue = {
  openLogin: (options?: OpenLoginOptions) => void;
  /** Alias for closing the login dialog. */
  close: () => void;
};

export const LoginModalContext = createContext<LoginModalContextValue | null>(
  null
);
