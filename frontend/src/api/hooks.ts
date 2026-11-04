import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { eventsService, type EventListParams } from "./services/events";
import { healthService } from "./services/health";
import { incidentsService, type IncidentListParams } from "./services/incidents";
import { workflowsService, type WorkflowListParams } from "./services/workflows";
import { analyticsService, type LifecycleAnalyticsParams } from "./services/analytics";
import { overviewService } from "./services/overview";
import type { EventEnvelope, WorkflowState } from "./types";

export const workflowStateKeys: WorkflowState[] = ["RECEIVED", "QUEUED", "PROCESSING", "RETRY_WAIT", "COMPENSATING", "SUCCEEDED", "FAILED", "DEAD_LETTERED", "CANCELLED"];

export function useWorkflows(params: WorkflowListParams = {}, enabled = true) {
  return useQuery({ queryKey: ["workflows", "list", params], queryFn: () => workflowsService.list(params), enabled });
}

export function useWorkflow(workflowId: string, enabled = true) {
  return useQuery({ queryKey: ["workflows", "detail", workflowId], queryFn: () => workflowsService.get(workflowId), enabled: enabled && Boolean(workflowId), refetchInterval: (query) => ["RECEIVED", "QUEUED", "PROCESSING", "RETRY_WAIT", "COMPENSATING"].includes(query.state.data?.state ?? "") ? 5000 : false });
}

export function useWorkflowStateCounts(enabled = true) {
  const queries = useQueries({ queries: workflowStateKeys.map((state) => ({ queryKey: ["workflows", "count", state], queryFn: () => workflowsService.list({ state, page_size: 1 }), enabled })) });
  const counts = Object.fromEntries(workflowStateKeys.map((state, index) => [state, queries[index]?.data?.count ?? 0])) as Record<WorkflowState, number>;
  return {
    counts,
    isLoading: queries.some((query) => query.isLoading),
    isFetching: queries.some((query) => query.isFetching),
    isError: queries.some((query) => query.isError),
    error: queries.find((query) => query.isError)?.error,
    updatedAt: Math.max(0, ...queries.map((query) => query.dataUpdatedAt)),
    refetch: () => Promise.all(queries.map((query) => query.refetch())),
  };
}

export function useEvent(eventId: string, enabled = true) {
  return useQuery({ queryKey: ["events", "detail", eventId], queryFn: () => eventsService.get(eventId), enabled: enabled && Boolean(eventId) });
}

export function useEvents(params: EventListParams = {}, enabled = true) {
  return useQuery({ queryKey: ["events", "list", params], queryFn: () => eventsService.list(params), enabled });
}

export function useCreateEvent() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: (envelope: EventEnvelope) => eventsService.create(envelope), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["events", "list"] }); void queryClient.invalidateQueries({ queryKey: ["workflows"] }); void queryClient.invalidateQueries({ queryKey: ["workflows", "count"] }); } });
}

export function useCreateEventBatch() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: (envelopes: EventEnvelope[]) => eventsService.createBatch(envelopes), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["events", "list"] }); void queryClient.invalidateQueries({ queryKey: ["workflows"] }); void queryClient.invalidateQueries({ queryKey: ["workflows", "count"] }); } });
}

export function useCreateIncidentSummary(workflowId: string) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: () => incidentsService.createSummary(workflowId), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["incidents", "list"] }); } });
}

export function useIncidentSummaries(params: IncidentListParams = {}, enabled = true) {
  return useQuery({ queryKey: ["incidents", "list", params], queryFn: () => incidentsService.list(params), enabled });
}

export function useIncidentSummary(incidentId: string, enabled = true) {
  return useQuery({ queryKey: ["incidents", "detail", incidentId], queryFn: () => incidentsService.get(incidentId), enabled: enabled && Boolean(incidentId) });
}

export function useLifecycleAnalytics(params: LifecycleAnalyticsParams, enabled = true) {
  return useQuery({
    queryKey: ["analytics", "lifecycle", params],
    queryFn: () => analyticsService.lifecycle(params),
    enabled,
    staleTime: 120_000,
    refetchInterval: 300_000,
  });
}

export function useOverview(enabled = true) {
  return useQuery({
    queryKey: ["overview"],
    queryFn: overviewService.get,
    enabled,
    staleTime: 15_000,
    refetchInterval: 60_000,
  });
}

export function useHealthChecks(enabled = true) {
  const live = useQuery({ queryKey: ["health", "live"], queryFn: healthService.live, enabled, refetchInterval: 30_000 });
  const ready = useQuery({ queryKey: ["health", "ready"], queryFn: healthService.ready, enabled, refetchInterval: 30_000 });
  return { live, ready, isLoading: live.isLoading || ready.isLoading, error: live.error ?? ready.error, refetch: () => { void live.refetch(); void ready.refetch(); } };
}

export function useServiceHealth(enabled = true) {
  return useQuery({
    queryKey: ["health", "services"],
    queryFn: healthService.services,
    enabled,
    staleTime: 25_000,
    refetchInterval: 30_000,
  });
}
