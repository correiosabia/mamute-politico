import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AccountModal } from "./AccountModal";
import {
  fetchCurrentMember,
  updateMemberNewsletterSubscription,
} from "./fetchCurrentMember";
import type { CurrentMember } from "./fetchCurrentMember";

vi.mock("./fetchCurrentMember", async (importOriginal) => {
  const original = await importOriginal<typeof import("./fetchCurrentMember")>();
  return {
    ...original,
    deleteMyAccount: vi.fn(),
    fetchCurrentMember: vi.fn(),
    requestMemberEmailChange: vi.fn(),
    signOut: vi.fn(),
    updateMemberNewsletterSubscription: vi.fn(),
    updateMemberProfile: vi.fn(),
  };
});

vi.mock("@/components/auth/ghost-auth/react/useGhostAuth", () => ({
  ghostSignOut: vi.fn(),
}));

const currentMember: CurrentMember = {
  uuid: "member-uuid",
  email: "user@example.com",
  name: "Jamie",
  status: "comped",
  subscribed: true,
  newsletters: [{ id: "newsletter-1", name: "Mamute" }],
  subscriptions: [
    {
      status: "active",
      tier: { id: "tier-1", name: "Cidadão Mamute" },
      price: { amount: 0, currency: "BRL", interval: "month" },
    },
  ],
};

describe("AccountModal membership controls", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchCurrentMember).mockResolvedValue(currentMember);
  });

  it("shows the Ghost plan and newsletter preference", async () => {
    render(
      <AccountModal open onOpenChange={vi.fn()} launchKey={1} />
    );

    expect(await screen.findByText("Cidadão Mamute")).toBeInTheDocument();
    expect(screen.getByText("Cortesia")).toBeInTheDocument();
    expect(screen.getByText("Newsletter por e-mail")).toBeInTheDocument();
    expect(screen.getByText("Inscrito")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Alterar" })).toHaveAttribute(
      "href",
      "/#/portal/account/plans"
    );
  });

  it("updates the Ghost newsletter preference from the switch", async () => {
    vi.mocked(updateMemberNewsletterSubscription).mockResolvedValue({
      ...currentMember,
      subscribed: false,
      newsletters: [],
    });

    render(
      <AccountModal open onOpenChange={vi.fn()} launchKey={1} />
    );

    const newsletterSwitch = await screen.findByRole("switch", {
      name: "Newsletter por e-mail",
    });
    fireEvent.click(newsletterSwitch);

    await waitFor(() => {
      expect(updateMemberNewsletterSubscription).toHaveBeenCalledWith({
        subscribed: false,
      });
    });
    expect(await screen.findByText("Não inscrito")).toBeInTheDocument();
  });
});
