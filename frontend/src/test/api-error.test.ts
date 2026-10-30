import { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { afterEach, describe, expect, it } from "vitest";
import api from "../api/client";
import { getApiToken, setApiToken } from "../api/auth-token";

const originalAdapter = api.defaults.adapter;
afterEach(() => {
  api.defaults.adapter = originalAdapter;
  setApiToken(null);
});

function mockStatus(status: number, code: string) {
  api.defaults.adapter = (async (config) => {
    const response: AxiosResponse = {
      data: { error: { code, message: "Request denied", request_id: "request-test", details: {} } },
      status,
      statusText: status === 401 ? "Unauthorized" : "Forbidden",
      headers: new AxiosHeaders({ "x-request-id": "request-test" }),
      config,
    };
    throw new AxiosError("Request failed", AxiosError.ERR_BAD_REQUEST, config, undefined, response);
  }) as AxiosAdapter;
}

describe("API response error handling", () => {
  it("normalizes 403 responses and preserves request IDs without exposing stack text", async () => {
    mockStatus(403, "PERMISSION_DENIED");
    await expect(api.get("/api/v1/workflows")).rejects.toMatchObject({ status: 403, code: "PERMISSION_DENIED", requestId: "request-test" });
  });

  it("clears the in-memory client token after a 401 response", async () => {
    setApiToken("CLIENT-TEST.secret");
    mockStatus(401, "AUTHENTICATION_FAILED");
    await expect(api.get("/api/v1/workflows")).rejects.toMatchObject({ status: 401 });
    expect(getApiToken()).toBeNull();
  });
});
