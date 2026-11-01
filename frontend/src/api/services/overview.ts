import api from "../client";
import type { OverviewSummary } from "../types";

export const overviewService = {
  async get() {
    const response = await api.get<OverviewSummary>("/api/v1/analytics/overview");
    return response.data;
  },
};
