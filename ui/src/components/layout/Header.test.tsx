import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Header } from "./Header";

vi.mock("@/components/auth/ghost-auth/react/useGhostAuth", () => ({
  useGhostAuth: () => null,
}));

vi.mock("@/hooks/useIsAdmin", () => ({
  useIsAdmin: () => ({ isAdmin: false, isLoading: false }),
}));

// O Header lê a flag do sino; sem o mock o hook exigiria QueryClientProvider.
vi.mock("@/hooks/useFeatureFlag", () => ({
  useFeatureFlag: () => false,
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

function expectParceriasNewTab(link: HTMLElement) {
  expect(link).toHaveAttribute("href", SEJA_PARCEIRO_URL);
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
}

describe("Header — grupo Contato", () => {
  it("expõe Contato como gatilho de submenu, não como link", () => {
    renderHeader();

    // Com a gaveta mobile fechada (aria-hidden), só a nav desktop é acessível.
    const gatilho = screen.getByRole("button", { name: "Contato" });
    expect(gatilho).toHaveAttribute("aria-expanded", "false");
    // Não existe página de contato: o item nunca navega para lugar nenhum.
    expect(screen.queryByRole("link", { name: "Contato" })).toBeNull();
  });

  it("mantém o submenu fechado até alguém abrir", () => {
    renderHeader();

    expect(screen.queryByRole("link", { name: "Blog" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Parcerias" })).toBeNull();
  });

  it("abre Parcerias e Blog no submenu desktop, nessa ordem", () => {
    renderHeader();

    fireEvent.click(screen.getByRole("button", { name: "Contato" }));

    expectParceriasNewTab(screen.getByRole("link", { name: "Parcerias" }));
    expect(screen.getByRole("link", { name: "Blog" })).toHaveAttribute("href", "/#/");

    // A ordem é requisito da demanda: Parcerias em cima, Blog embaixo.
    const submenu = document.getElementById("nav-submenu-contato") as HTMLElement;
    expect(within(submenu).getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Parcerias",
      "Blog",
    ]);
  });

  it("abre quando o foco entra no grupo e fecha com Escape", () => {
    renderHeader();

    const gatilho = screen.getByRole("button", { name: "Contato" });

    fireEvent.focus(gatilho);
    expect(screen.getByRole("link", { name: "Blog" })).toBeInTheDocument();

    fireEvent.keyDown(gatilho, { key: "Escape" });
    expect(screen.queryByRole("link", { name: "Blog" })).toBeNull();
  });

  it("mostra Parcerias e Blog recuados na gaveta mobile, sem exigir toque extra", () => {
    renderHeader();

    fireEvent.click(screen.getByRole("button", { name: "Abrir menu" }));

    // Com a gaveta aberta, a nav desktop também fica acessível: escopo na gaveta.
    const gaveta = within(document.getElementById("mobile-header-drawer") as HTMLElement);
    expect(gaveta.getByRole("link", { name: "Blog" })).toHaveAttribute("href", "/#/");
    expectParceriasNewTab(gaveta.getByRole("link", { name: "Parcerias" }));
    // Na gaveta "Contato" é só rótulo: nem link, nem botão de abrir/fechar.
    expect(gaveta.getByText("Contato")).toBeInTheDocument();
    expect(gaveta.queryByRole("button", { name: "Contato" })).toBeNull();
  });

  it("não deixa mais Parcerias no primeiro nível — só dentro do submenu", () => {
    renderHeader();

    const nav = screen.getByRole("button", { name: "Contato" }).closest("nav") as HTMLElement;
    expect(within(nav).queryByRole("link", { name: "Parcerias" })).toBeNull();
  });
});
