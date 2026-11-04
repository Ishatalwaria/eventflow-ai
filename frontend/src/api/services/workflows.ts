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
  async command(workflowId: string, action: "retry" | "replay" | "cancel") {
    const response = await api.post<{ workflow_id: string; state: string; current_stage: string; audit_id: string }>(
      "/api/v1/workflows/" + encodeURIComponent(workflowId) + "/" + action,
      {},
      { headers: { "Idempotency-Key": crypto.randomUUID() } },
    );
    return response.data;
  },
};
