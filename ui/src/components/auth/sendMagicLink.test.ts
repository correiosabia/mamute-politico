import axios from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  sendMagicLinkUnified,
  isMemberNotFoundError,
} from "./sendMagicLink";

vi.mock("axios");
vi.mock("./config", () => ({
  GHOST_VERSION: "test",
  INTEGRITY_TOKEN_ENDPOINT: "https://ghost.test/members/api/integrity-token/",
  MAGIC_LINK_ENDPOINT: "https://ghost.test/members/api/send-magic-link/",
}));

const mockedAxios = vi.mocked(axios);

function mockIntegrityToken() {
  mockedAxios.get.mockResolvedValue({
    status: 200,
    data: "integrity-token",
  } as never);
}

function mockMagicLinkPost(
  ...responses: Array<{ status: number; data?: unknown }>
) {
  for (const response of responses) {
    mockedAxios.post.mockResolvedValueOnce(response as never);
  }
}

describe("sendMagicLinkUnified", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIntegrityToken();
  });

  it("returns signin when signin magic link succeeds", async () => {
    mockMagicLinkPost({ status: 201 });

    const result = await sendMagicLinkUnified({ email: "user@example.com" });

    expect(result).toEqual({ emailType: "signin" });
    expect(mockedAxios.post).toHaveBeenCalledTimes(1);
    expect(mockedAxios.post.mock.calls[0]?.[1]).toMatchObject({
      email: "user@example.com",
      emailType: "signin",
    });
  });

  it("falls back to signup when signin reports member not found", async () => {
    mockMagicLinkPost(
      {
        status: 404,
        data: { errors: [{ message: "Member not found" }] },
      },
      { status: 201 }
    );

    const result = await sendMagicLinkUnified({ email: "new@example.com" });

    expect(result).toEqual({ emailType: "signup" });
    expect(mockedAxios.post).toHaveBeenCalledTimes(2);
    expect(mockedAxios.post.mock.calls[1]?.[1]).toMatchObject({
      email: "new@example.com",
      emailType: "signup",
    });
  });

  it("does not call signup when signin fails for other reasons", async () => {
    mockMagicLinkPost({
      status: 500,
      data: { errors: [{ message: "Failed to send email" }] },
    });

    await expect(
      sendMagicLinkUnified({ email: "user@example.com" })
    ).rejects.toThrow("Failed to send email");

    expect(mockedAxios.post).toHaveBeenCalledTimes(1);
  });
});

describe("isMemberNotFoundError", () => {
  it("detects Ghost member-not-found messages", () => {
    const err = Object.assign(new Error("Member not found"), {
      ghostMessage: "Member not found",
    });
    expect(isMemberNotFoundError(err)).toBe(true);
    expect(isMemberNotFoundError(new Error("Failed to send email"))).toBe(
      false
    );
  });
});
