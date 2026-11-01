import api from "../client";
import type { HealthResponse, ServiceHealthSummary } from "../types";

export const healthService = {
  async live() {
    const response = await api.get<HealthResponse>("/health/live");
    return response.data;
  },
  async ready() {
    const response = await api.get<HealthResponse>("/health/ready");
    return response.data;
  },
  async services() {
    const response = await api.get<ServiceHealthSummary>("/health/services");
    return response.data;
  },
};
