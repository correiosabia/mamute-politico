import type { CurrentMember, MemberSubscription } from "./fetchCurrentMember";

const ACTIVE_SUBSCRIPTION_STATUSES = new Set([
  "active",
  "trialing",
  "unpaid",
  "past_due",
]);

export type MemberPlanDetails = {
  name: string;
  description: string;
};

function activeSubscription(
  member: CurrentMember
): MemberSubscription | undefined {
  return (
    member.subscriptions?.find((subscription) =>
      ACTIVE_SUBSCRIPTION_STATUSES.has(subscription.status ?? "")
    ) ?? member.subscriptions?.[0]
  );
}

function formatPrice(subscription: MemberSubscription | undefined): string | null {
  const { amount, currency, interval } = subscription?.price ?? {};
  if (typeof amount !== "number" || !currency || amount <= 0) return null;

  const price = new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency,
  }).format(amount / 100);
  const cadence = interval === "year" ? "ano" : "mês";
  return `${price}/${cadence}`;
}

export function getMemberPlanDetails(
  member: CurrentMember
): MemberPlanDetails {
  const subscription = activeSubscription(member);
  const fallbackTier = member.tiers?.[member.tiers.length - 1];
  const name =
    subscription?.tier?.name?.trim() ||
    fallbackTier?.name?.trim() ||
    (member.status === "free" ? "Plano gratuito" : "Plano Mamute");

  if (
    member.status === "comped" ||
    member.comped === true ||
    (member.status !== "free" && subscription?.price?.amount === 0)
  ) {
    return { name, description: "Cortesia" };
  }

  if (member.status === "free") {
    return { name, description: "Gratuito" };
  }

  return {
    name,
    description: formatPrice(subscription) ?? "Assinatura ativa",
  };
}

export function isMemberSubscribedToNewsletter(
  member: CurrentMember
): boolean {
  if (member.subscribed !== undefined) return member.subscribed;
  return Boolean(member.newsletters?.length);
}
