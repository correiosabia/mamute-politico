import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { RootRoute } from "./App";

// Usuário LOGADO — era exatamente nesse caso que a raiz redirecionava para /selecao.
vi.mock("@/components/auth/ghost-auth/react/useGhostAuth", () => ({
  useGhostAuth: () => "fake-token",
}));

vi.mock("@/hooks/useIsAdmin", () => ({
  useIsAdmin: () => ({ isAdmin: false, isLoading: false }),
}));

vi.mock("@/components/auth/useLoginModal", () => ({
  useLoginModal: () => ({ openLogin: vi.fn() }),
}));

vi.mock("@/components/auth/useAccountModal", () => ({
  useAccountModal: () => ({ openAccount: vi.fn() }),
}));

describe("RootRoute", () => {
  it("mostra a tela de Início na raiz mesmo com usuário logado (não redireciona para /selecao)", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<RootRoute />} />
          <Route path="/selecao" element={<div>SELECAO_STUB</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(
      screen.getByRole("heading", { name: /Monitore políticos do Congresso/i })
    ).toBeInTheDocument();
    expect(screen.queryByText("SELECAO_STUB")).not.toBeInTheDocument();
  });
});
