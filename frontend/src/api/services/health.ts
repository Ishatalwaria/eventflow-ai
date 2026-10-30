import api from "../client";
import type { HealthResponse } from "../types";

export const healthService = {
  async live() {
    const response = await api.get<HealthResponse>("/health/live");
    return response.data;
  },
  async ready() {
    const response = await api.get<HealthResponse>("/health/ready");
    return response.data;
  },
};
