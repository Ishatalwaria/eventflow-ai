import api from "../client";
import type { IncidentSummary, IncidentSummaryListItem, Paginated, WorkflowState } from "../types";

export interface IncidentListParams {
  page?: number;
  page_size?: number;
  search?: string;
  workflow_state?: Extract<WorkflowState, "FAILED" | "DEAD_LETTERED">;
}

export const incidentsService = {
  async list(params: IncidentListParams = {}) {
    const response = await api.get<Paginated<IncidentSummaryListItem>>("/api/v1/incidents", { params });
    return response.data;
  },
  async get(incidentId: string) {
    const response = await api.get<IncidentSummary>("/api/v1/incidents/" + encodeURIComponent(incidentId));
    return response.data;
  },
  async createSummary(workflowId: string) {
    const response = await api.post<IncidentSummary>("/api/v1/workflows/" + encodeURIComponent(workflowId) + "/incident-summary");
    return response.data;
  },
};
