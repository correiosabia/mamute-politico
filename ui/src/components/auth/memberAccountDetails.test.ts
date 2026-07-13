import { describe, expect, it } from "vitest";
import {
  getMemberPlanDetails,
  isMemberSubscribedToNewsletter,
} from "./memberAccountDetails";
import type { CurrentMember } from "./fetchCurrentMember";

const member: CurrentMember = {
  uuid: "member-uuid",
  email: "user@example.com",
  name: "Jamie",
};

describe("getMemberPlanDetails", () => {
  it("shows a complimentary Ghost tier", () => {
    expect(
      getMemberPlanDetails({
        ...member,
        status: "comped",
        subscriptions: [
          {
            status: "active",
            tier: { id: "tier-1", name: "Cidadão Mamute" },
            price: { amount: 0, currency: "BRL", interval: "month" },
          },
        ],
      })
    ).toEqual({ name: "Cidadão Mamute", description: "Cortesia" });
  });

  it("formats the active paid subscription", () => {
    expect(
      getMemberPlanDetails({
        ...member,
        status: "paid",
        subscriptions: [
          {
            status: "active",
            tier: { name: "Mamute Premium" },
            price: { amount: 4990, currency: "BRL", interval: "month" },
          },
        ],
      })
    ).toEqual({ name: "Mamute Premium", description: "R$ 49,90/mês" });
  });

  it("falls back to the member tier for free accounts", () => {
    expect(
      getMemberPlanDetails({
        ...member,
        status: "free",
        tiers: [{ name: "Leitor Mamute" }],
      })
    ).toEqual({ name: "Leitor Mamute", description: "Gratuito" });
  });
});

describe("isMemberSubscribedToNewsletter", () => {
  it("prefers Ghost's subscribed flag when available", () => {
    expect(
      isMemberSubscribedToNewsletter({
        ...member,
        subscribed: false,
        newsletters: [{ id: "newsletter-1" }],
      })
    ).toBe(false);
  });

  it("falls back to the newsletter relation", () => {
    expect(
      isMemberSubscribedToNewsletter({
        ...member,
        newsletters: [{ id: "newsletter-1" }],
      })
    ).toBe(true);
  });
});
