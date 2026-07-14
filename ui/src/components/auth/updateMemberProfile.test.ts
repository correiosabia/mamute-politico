import axios from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchCurrentMember,
  fetchIdentityToken,
  requestMemberEmailChange,
  updateMemberNewsletterSubscription,
  updateMemberProfile,
} from "./fetchCurrentMember";

vi.mock("axios");
vi.mock("./config", () => ({
  GHOST_VERSION: "test",
  TOKEN_ENDPOINT: "https://ghost.test/members/api/session/",
  MEMBER_ENDPOINT: "https://ghost.test/members/api/member/",
  MEMBER_EMAIL_ENDPOINT: "https://ghost.test/members/api/member/email",
}));

const mockedAxios = vi.mocked(axios);

describe("fetchCurrentMember", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("preserves Ghost plan and newsletter data used by the account modal", async () => {
    mockedAxios.get.mockResolvedValue({
      status: 200,
      data: {
        uuid: "member-uuid",
        email: "user@example.com",
        name: "Jamie",
        status: "comped",
        subscribed: true,
        comped: true,
        newsletters: [{ id: "newsletter-1", name: "Mamute" }],
        tiers: [{ id: "tier-1", name: "Cidadão Mamute" }],
        subscriptions: [
          {
            id: "subscription-1",
            status: "active",
            tier: { id: "tier-1", name: "Cidadão Mamute" },
            price: { amount: 0, currency: "BRL", interval: "month" },
          },
        ],
      },
    } as never);

    await expect(fetchCurrentMember()).resolves.toMatchObject({
      status: "comped",
      subscribed: true,
      comped: true,
      newsletters: [{ id: "newsletter-1", name: "Mamute" }],
      tiers: [{ id: "tier-1", name: "Cidadão Mamute" }],
      subscriptions: [
        {
          status: "active",
          tier: { id: "tier-1", name: "Cidadão Mamute" },
        },
      ],
    });
  });
});

describe("fetchIdentityToken", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns trimmed token on success", async () => {
    mockedAxios.get.mockResolvedValue({
      status: 200,
      data: " identity-token ",
    } as never);

    await expect(fetchIdentityToken()).resolves.toBe("identity-token");
  });

  it("throws when session token is missing", async () => {
    mockedAxios.get.mockResolvedValue({ status: 204, data: "" } as never);

    await expect(fetchIdentityToken()).rejects.toThrow(
      "Não foi possível obter token de sessão"
    );
  });
});

describe("updateMemberProfile", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sends PUT with trimmed name and returns parsed member", async () => {
    mockedAxios.put.mockResolvedValue({
      status: 200,
      data: {
        uuid: "member-uuid",
        email: "user@example.com",
        name: "Jamie",
      },
    } as never);

    const result = await updateMemberProfile({ name: "  Jamie  " });

    expect(result).toEqual({
      uuid: "member-uuid",
      email: "user@example.com",
      name: "Jamie",
      status: undefined,
    });
    expect(mockedAxios.put).toHaveBeenCalledWith(
      "https://ghost.test/members/api/member/",
      { name: "Jamie" },
      expect.objectContaining({
        withCredentials: true,
      })
    );
  });

  it("sends null name when cleared", async () => {
    mockedAxios.put.mockResolvedValue({
      status: 200,
      data: {
        uuid: "member-uuid",
        email: "user@example.com",
        name: null,
      },
    } as never);

    await updateMemberProfile({ name: "   " });

    expect(mockedAxios.put.mock.calls[0]?.[1]).toEqual({ name: null });
  });

  it("propagates Ghost error messages", async () => {
    mockedAxios.put.mockResolvedValue({
      status: 422,
      data: { errors: [{ message: "Member already exists." }] },
    } as never);

    await expect(updateMemberProfile({ name: "Jamie" })).rejects.toThrow(
      "Member already exists."
    );
  });
});

describe("updateMemberNewsletterSubscription", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("updates the default Ghost newsletter preference", async () => {
    mockedAxios.put.mockResolvedValue({
      status: 200,
      data: {
        uuid: "member-uuid",
        email: "user@example.com",
        name: "Jamie",
        subscribed: false,
        newsletters: [],
      },
    } as never);

    const result = await updateMemberNewsletterSubscription({
      subscribed: false,
    });

    expect(result.subscribed).toBe(false);
    expect(result.newsletters).toEqual([]);
    expect(mockedAxios.put).toHaveBeenCalledWith(
      "https://ghost.test/members/api/member/",
      { subscribed: false },
      expect.objectContaining({ withCredentials: true })
    );
  });

  it("propagates Ghost errors", async () => {
    mockedAxios.put.mockResolvedValue({
      status: 422,
      data: { errors: [{ message: "Newsletter unavailable." }] },
    } as never);

    await expect(
      updateMemberNewsletterSubscription({ subscribed: true })
    ).rejects.toThrow("Newsletter unavailable.");
  });
});

describe("requestMemberEmailChange", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches identity token then POSTs email change request", async () => {
    mockedAxios.get.mockResolvedValue({
      status: 200,
      data: "identity-token",
    } as never);
    mockedAxios.post.mockResolvedValue({ status: 201 } as never);

    await requestMemberEmailChange({ email: "  new@example.com  " });

    expect(mockedAxios.get).toHaveBeenCalledWith(
      "https://ghost.test/members/api/session/",
      expect.objectContaining({ withCredentials: true })
    );
    expect(mockedAxios.post).toHaveBeenCalledWith(
      "https://ghost.test/members/api/member/email",
      { identity: "identity-token", email: "new@example.com" },
      expect.objectContaining({ withCredentials: true })
    );
  });

  it("propagates Ghost error messages from email change", async () => {
    mockedAxios.get.mockResolvedValue({
      status: 200,
      data: "identity-token",
    } as never);
    mockedAxios.post.mockResolvedValue({
      status: 422,
      data: { errors: [{ message: "Member already exists." }] },
    } as never);

    await expect(
      requestMemberEmailChange({ email: "taken@example.com" })
    ).rejects.toThrow("Member already exists.");
  });
});
