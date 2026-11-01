import { afterEach, describe, expect, it, vi } from "vitest";
import { AxiosError, type InternalAxiosRequestConfig } from "axios";
import api, { ApiRequestError } from "../api/client";
import { clearApiToken, setApiToken } from "../api/auth-token";

const originalAdapter = api.defaults.adapter;

describe("API client authorization", () => {
  afterEach(() => {
    clearApiToken();
    api.defaults.adapter = originalAdapter;
    vi.restoreAllMocks();
  });

  it("sends the in-memory client token to the protected service health endpoint", async () => {
    setApiToken("client-id.client-secret");
    const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => ({
      data: { status: "ok" },
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    }));
    api.defaults.adapter = adapter;

    await api.get("/health/services");

    expect(adapter).toHaveBeenCalledOnce();
    expect(adapter.mock.calls[0][0].headers.Authorization).toBe("Bearer client-id.client-secret");
  });

  it("does not send the client token to public health endpoints", async () => {
    setApiToken("client-id.client-secret");
    const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => ({
      data: { status: "ok" },
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    }));
    api.defaults.adapter = adapter;

    await api.get("/health/live");

    expect(adapter.mock.calls[0][0].headers.Authorization).toBeUndefined();
  });

  it("shows the API permission detail for a forbidden analytics request", async () => {
    const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => {
      throw new AxiosError("Forbidden", "ERR_BAD_REQUEST", config, undefined, {
        data: {
          error: {
            code: "PERMISSION_DENIED",
            message: "The request could not be completed.",
            request_id: "request-403",
            details: { detail: "This API client does not have analytics access." },
          },
        },
        status: 403,
        statusText: "Forbidden",
        headers: {},
        config,
      });
    });
    api.defaults.adapter = adapter;

    await expect(api.get("/api/v1/analytics/lifecycle")).rejects.toMatchObject({
      message: "This API client does not have analytics access.",
      code: "PERMISSION_DENIED",
    } satisfies Partial<ApiRequestError>);
  });
});
