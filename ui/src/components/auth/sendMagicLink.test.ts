import axios from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sendMagicLinkUnified } from "./sendMagicLink";

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

  it("uses Ghost subscribe flow for combined sign-in and sign-up", async () => {
    mockMagicLinkPost({ status: 201 });

    const result = await sendMagicLinkUnified({ email: " user@example.com " });

    expect(result).toEqual({ emailType: "subscribe" });
    expect(mockedAxios.post).toHaveBeenCalledTimes(1);
    expect(mockedAxios.post.mock.calls[0]?.[1]).toMatchObject({
      email: "user@example.com",
      emailType: "subscribe",
    });
  });

  it("propagates Ghost errors without retrying", async () => {
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
