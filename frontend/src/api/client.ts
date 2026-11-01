import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import type { ApiError } from "./types";
import { clearApiToken, getApiToken } from "./auth-token";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const requestBaseUrl = import.meta.env.DEV ? "" : API_BASE_URL.replace(/\/$/, "");

export class ApiRequestError extends Error {
  readonly status: number | undefined;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: unknown;

  constructor(message: string, options: { status?: number; code?: string; requestId?: string | null; details?: unknown } = {}) {
    super(message);
    this.name = "ApiRequestError";
    this.status = options.status;
    this.code = options.code ?? "API_ERROR";
    this.requestId = options.requestId ?? null;
    this.details = options.details;
  }
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(^|;\\s*)(" + name + ")=([^;]*)"));
  return match ? decodeURIComponent(match[3]) : null;
}

const api = axios.create({
  baseURL: requestBaseUrl,
  timeout: 12_000,
  withCredentials: true,
  headers: { Accept: "application/json", "Content-Type": "application/json" },
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getApiToken();
  const requiresClientToken = config.url?.startsWith("/api/v1/") || config.url === "/health/services";
  if (token && requiresClientToken) config.headers.Authorization = "Bearer " + token;
  else delete config.headers.Authorization;

  const csrfToken = getCookie("csrftoken");
  if (csrfToken && config.method && !["get", "head", "options"].includes(config.method.toLowerCase())) {
    config.headers["X-CSRFToken"] = csrfToken;
  }

  if (!config.headers["X-Request-ID"]) config.headers["X-Request-ID"] = crypto.randomUUID();
  return config;
});

function errorFromResponse(error: AxiosError<ApiError>) {
  const status = error.response?.status;
  const envelope = error.response?.data?.error;
  const detail = envelope?.details && typeof envelope.details === "object" && "detail" in envelope.details
    ? (envelope.details as { detail?: unknown }).detail
    : undefined;
  const requestId = envelope?.request_id ?? error.response?.headers["x-request-id"] ?? null;
  const code = envelope?.code ?? "API_ERROR";
  const messages: Record<number, string> = {
    401: "Your API client token is missing, invalid, or revoked. Re-enter a valid token in Settings.",
    403: typeof detail === "string" ? detail : envelope?.message ?? "The API denied this request. Check the client permissions and endpoint access.",
    404: "The requested record was not found or is not accessible to this client.",
    429: envelope?.message ?? "The API rate limit was reached. Wait before trying again.",
    500: "The API encountered an internal error.",
    502: envelope?.message ?? "An upstream service returned an invalid response.",
    503: envelope?.message ?? "A required service is temporarily unavailable.",
    413: "The request is larger than the API allows.",
  };
  const message = status ? messages[status] ?? envelope?.message ?? "The API returned HTTP " + status + "." :
    error.code === "ECONNABORTED" ? "The API request timed out. Try again." :
      "Could not reach the API at " + API_BASE_URL + ". Check the API URL and connection.";
  if (status === 401 && getApiToken()) {
    clearApiToken();
    if (typeof window !== "undefined") window.dispatchEvent(new Event("eventflow:unauthorized"));
  }
  return new ApiRequestError(message, { status, code, requestId, details: envelope?.details });
}

api.interceptors.response.use(
  (response) => response,
  (error: unknown) => axios.isAxiosError<ApiError>(error) ? Promise.reject(errorFromResponse(error)) : Promise.reject(error),
);

export function apiErrorMessage(error: unknown) {
  if (error instanceof ApiRequestError) return error.requestId ? error.message + " (request " + error.requestId + ")" : error.message;
  if (axios.isAxiosError(error)) {
    if (error.code === "ECONNABORTED") return "The API request timed out. Try again.";
    if (!error.response) return "Could not reach the API at " + API_BASE_URL + ". Check the API URL and connection.";
  }
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}

export default api;
