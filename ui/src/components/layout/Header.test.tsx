import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Header } from "./Header";

vi.mock("@/components/auth/ghost-auth/react/useGhostAuth", () => ({
  useGhostAuth: () => null,
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

function renderHeader() {
  return render(
    <MemoryRouter>
      <Header />
    </MemoryRouter>
  );
}

const SEJA_PARCEIRO_URL = "https://mamutepolitico.com.br/seja-parceiro/";

function expectSejaParceiroNewTab(link: HTMLElement) {
  expect(link).toHaveAttribute("href", SEJA_PARCEIRO_URL);
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
}

describe("Header nav item Parcerias", () => {
  it("shows Parcerias in the desktop nav, opening Seja Parceiro in a new tab", () => {
    renderHeader();

    // Com a gaveta mobile fechada (aria-hidden), só a nav desktop é acessível.
    const link = screen.getByRole("link", { name: "Parcerias" });
    expectSejaParceiroNewTab(link);
  });

  it("shows Parcerias in the mobile nav once the drawer is open", () => {
    renderHeader();

    fireEvent.click(screen.getByRole("button", { name: "Abrir menu" }));

    // Com a gaveta aberta, tanto a nav desktop quanto a mobile expõem o item.
    const links = screen.getAllByRole("link", { name: "Parcerias" });
    expect(links).toHaveLength(2);
    links.forEach(expectSejaParceiroNewTab);
  });
});
