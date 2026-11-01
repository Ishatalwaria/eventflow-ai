import api from "../client";
import type {
  APIClientRecord,
  AuthLoginResponse,
  AuthRegisterResponse,
  CreatedAPIClientRecord,
  UserProfile,
} from "../types";

export const authService = {
  async csrf(): Promise<{ csrfToken: string }> {
    const response = await api.get<{ csrfToken: string }>("/api/v1/auth/csrf");
    return response.data;
  },

  async login(credentials: { email: string; password: string }): Promise<AuthLoginResponse> {
    // ensure csrf cookie is initialized
    await this.csrf();
    const response = await api.post<AuthLoginResponse>("/api/v1/auth/login", credentials);
    return response.data;
  },

  async register(payload: {
    name: string;
    email: string;
    password: string;
    password_confirm: string;
  }): Promise<AuthRegisterResponse> {
    await this.csrf();
    const response = await api.post<AuthRegisterResponse>("/api/v1/auth/register", payload);
    return response.data;
  },

  async logout(): Promise<void> {
    await api.post("/api/v1/auth/logout");
  },

  async getCurrentUser(): Promise<UserProfile> {
    const response = await api.get<UserProfile>("/api/v1/auth/me");
    return response.data;
  },

  async requestPasswordReset(email: string): Promise<{ detail: string }> {
    await this.csrf();
    const response = await api.post<{ detail: string }>("/api/v1/auth/password-reset", { email });
    return response.data;
  },

  async listClients(): Promise<{ count: number; results: APIClientRecord[] }> {
    const response = await api.get<{ count: number; results: APIClientRecord[] }>("/api/v1/clients");
    return response.data;
  },

  async createClient(payload: {
    name: string;
    can_view_analytics?: boolean;
  }): Promise<CreatedAPIClientRecord> {
    await this.csrf();
    const response = await api.post<CreatedAPIClientRecord>("/api/v1/clients", payload);
    return response.data;
  },

  async revokeClient(clientId: string): Promise<{ detail: string }> {
    await this.csrf();
    const response = await api.post<{ detail: string }>(`/api/v1/clients/${clientId}/revoke`);
    return response.data;
  },
};
