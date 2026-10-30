import api from "../client";
import type { IncidentSummary } from "../types";

export const incidentsService = {
  async createSummary(workflowId: string) {
    const response = await api.post<IncidentSummary>("/api/v1/workflows/" + encodeURIComponent(workflowId) + "/incident-summary");
    return response.data;
  },
};
