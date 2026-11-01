import api from "../client";
import type { LifecycleAnalytics } from "../types";

export interface LifecycleAnalyticsParams {
  date_from: string;
  date_to: string;
}

export const analyticsService = {
  async lifecycle(params: LifecycleAnalyticsParams) {
    const response = await api.get<LifecycleAnalytics>("/api/v1/analytics/tenant-lifecycle", { params });
    return response.data;
  },
};
