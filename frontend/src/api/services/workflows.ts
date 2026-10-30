import api from "../client";
import type { Paginated, Workflow, WorkflowState } from "../types";

export interface WorkflowListParams { page?: number; page_size?: number; state?: WorkflowState }

export const workflowsService = {
  async list(params: WorkflowListParams = {}) {
    const response = await api.get<Paginated<Workflow>>("/api/v1/workflows", { params });
    return response.data;
  },
  async get(workflowId: string) {
    const response = await api.get<Workflow>("/api/v1/workflows/" + encodeURIComponent(workflowId));
    return response.data;
  },
};
