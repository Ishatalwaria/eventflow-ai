import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useEffect } from "react";
import { ApiRequestError, apiErrorMessage } from "../api/client";
import { eventsService } from "../api/services/events";
import { healthService } from "../api/services/health";
import { incidentsService } from "../api/services/incidents";
import { analyticsService } from "../api/services/analytics";
import { overviewService } from "../api/services/overview";
import { AnalyticsPage } from "../features/analytics/AnalyticsPage";
import { workflowsService } from "../api/services/workflows";
import { EmptyState, LoadingState } from "../components/layout";
import { eventDetailFixture, eventListFixture, failedWorkflowFixture, incidentListFixture, incidentSummaryFixture, lifecycleAnalyticsFixture, overviewFixture, serviceHealthFixture } from "./fixtures";
import { renderApp, renderComponent } from "./render";
import { AuthProvider, useAuth } from "../app/auth";

function AuthenticatedAnalyticsPage() {
  const auth = useAuth();
  useEffect(() => { auth.setToken("CLIENT-TEST.secret"); }, [auth]);
  return <AnalyticsPage />;
}

beforeEach(() => {
  vi.spyOn(eventsService, "get").mockResolvedValue(eventDetailFixture);
  vi.spyOn(eventsService, "list").mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
  vi.spyOn(eventsService, "create").mockResolvedValue({ event_id: eventDetailFixture.id, workflow_id: failedWorkflowFixture.id, workflow_state: "RECEIVED", duplicate: false });
  vi.spyOn(workflowsService, "get").mockResolvedValue(failedWorkflowFixture);
  vi.spyOn(incidentsService, "createSummary").mockResolvedValue(incidentSummaryFixture);
  vi.spyOn(incidentsService, "list").mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
  vi.spyOn(incidentsService, "get").mockResolvedValue(incidentSummaryFixture);
  vi.spyOn(analyticsService, "lifecycle").mockResolvedValue(lifecycleAnalyticsFixture);
  vi.spyOn(overviewService, "get").mockResolvedValue(overviewFixture);
  vi.spyOn(workflowsService, "list").mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
  vi.spyOn(healthService, "live").mockResolvedValue({ status: "ok" });
  vi.spyOn(healthService, "ready").mockResolvedValue({ status: "ready", checks: { database: "ok" } });
  vi.spyOn(healthService, "services").mockResolvedValue(serviceHealthFixture);
});

describe("EventFlow frontend integration", () => {
  it("navigates between application sections", async () => {
    const user = userEvent.setup();
    renderApp("/events", "");
    expect(await screen.findByText("API connection required")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Settings" }));
    expect(await screen.findByText("Backend connection")).toBeInTheDocument();
  });

  it("renders historical event rows from the paginated backend collection", async () => {
    vi.spyOn(eventsService, "list").mockResolvedValue({ count: 9, next: "?page=2", previous: null, results: [eventListFixture] });
    renderApp("/events");
    expect(await screen.findByText("Event history")).toBeInTheDocument();
    expect(await screen.findByText("checkout-web")).toBeInTheDocument();
    expect(screen.getByText("idempotency-001")).toBeInTheDocument();
    expect(eventsService.list).toHaveBeenCalledWith({ page: 1, page_size: 8 });
    await userEvent.setup().click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(eventsService.list).toHaveBeenCalledWith({ page: 2, page_size: 8 }));
  });

  it("renders actual tenant summary data on the Overview page", async () => {
    renderApp("/overview");
    expect(await screen.findByText("EventFlow AI Overview")).toBeInTheDocument();
    expect(await screen.findByText("Total events")).toBeInTheDocument();
    expect(await screen.findByText("order.created")).toBeInTheDocument();
    expect(screen.getByText("Outbox backlog")).toBeInTheDocument();
    expect(overviewService.get).toHaveBeenCalledOnce();
  });

  it("renders service probes and only available operational metrics", async () => {
    renderApp("/health");
    expect(await screen.findByText("Service status")).toBeInTheDocument();
    expect(screen.getByText("Kafka")).toBeInTheDocument();
    expect(screen.getByText("Unavailable", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("LLM provider")).toBeInTheDocument();
    expect(screen.getAllByText("Not checked").length).toBeGreaterThan(0);
    expect(screen.getByText("Average API request latency")).toBeInTheDocument();
    expect(screen.getByText("Average LLM latency")).toBeInTheDocument();
  });

  it("sends event search and date filters to the backend", async () => {
    const user = userEvent.setup();
    renderApp("/events");
    await user.type(screen.getByRole("textbox", { name: "Search events" }), "checkout-001");
    fireEvent.change(screen.getByLabelText("Received from date"), { target: { value: "2026-10-01" } });
    await waitFor(() => expect(eventsService.list).toHaveBeenCalledWith(expect.objectContaining({ search: "checkout-001", date_from: "2026-10-01" })), { timeout: 2500 });
  });

  it("shows a retryable error when event history is unavailable", async () => {
    vi.spyOn(eventsService, "list").mockRejectedValue(new Error("API unavailable"));
    const user = userEvent.setup();
    renderApp("/events");
    expect(await screen.findByText("Event history unavailable")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(eventsService.list).toHaveBeenCalledTimes(2));
  });

  it("validates and submits a single event using the backend envelope", async () => {
    const user = userEvent.setup();
    renderApp("/events");
    const payload = screen.getByLabelText("Payload JSON");
    await user.clear(payload);
    fireEvent.change(payload, { target: { value: '{"order_id":"order-001","currency":"INR","total_minor_units":1234,"items":[{"sku":"SKU-1","quantity":1}]}' } });
    await user.click(screen.getByRole("button", { name: "Submit event" }));
    await waitFor(() => expect(eventsService.create).toHaveBeenCalledOnce());
    expect(eventsService.create).toHaveBeenCalledWith(expect.objectContaining({ event_type: "order.created", schema_version: 1, payload: { order_id: "order-001", currency: "INR", total_minor_units: 1234, items: [{ sku: "SKU-1", quantity: 1 }] } }));
  });

  it("shows sanitized workflow attempt details and timeline", async () => {
    renderApp(`/workflows/${failedWorkflowFixture.id}`);
    expect(await screen.findByText("Execution timeline")).toBeInTheDocument();
    expect(screen.getAllByText("order validation", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getByText("Workflow attempts")).toBeInTheDocument();
    expect(screen.getAllByText(/REDACTED_EMAIL/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/person@example.com|hunter2/)).not.toBeInTheDocument();
  });

  it("renders AI analysis facts, hypotheses, unknowns, and diagnostic suggestions", async () => {
    const user = userEvent.setup();
    renderApp(`/incidents/workflow/${failedWorkflowFixture.id}`);
    await user.click(await screen.findByRole("button", { name: "Analyze failure" }));
    expect((await screen.findAllByText("Order validation rejected the request")).length).toBe(2);
    expect(screen.getByText("Confirmed facts")).toBeInTheDocument();
    expect(screen.getByText("AI hypotheses")).toBeInTheDocument();
    expect(screen.getByText("Unknowns")).toBeInTheDocument();
    expect(screen.getByText("Recommended diagnostic checks")).toBeInTheDocument();
    expect(screen.getByText("health-metrics:workflow-001")).toBeInTheDocument();
  });

  it("lists and reopens a persisted incident after navigating by incident ID", async () => {
    vi.spyOn(incidentsService, "list").mockResolvedValue({ count: 1, next: null, previous: null, results: [incidentListFixture] });
    renderApp("/incidents");
    expect(await screen.findByText("Incident history")).toBeInTheDocument();
    expect(await screen.findByText("test-provider · test-model")).toBeInTheDocument();
    await userEvent.setup().click(await screen.findByRole("link", { name: "Review" }));
    expect(await screen.findByText("Confirmed facts")).toBeInTheDocument();
    expect(incidentsService.get).toHaveBeenCalledWith(incidentSummaryFixture.id);
  });

  it("loads a persisted incident directly after a page reload", async () => {
    renderApp(`/incidents/id/${incidentSummaryFixture.id}`);
    expect(await screen.findByText("Confirmed facts")).toBeInTheDocument();
    expect(incidentsService.get).toHaveBeenCalledWith(incidentSummaryFixture.id);
  });

  it("renders tenant analytics and refreshes the selected range", async () => {
    const user = userEvent.setup();
    renderComponent(<AuthProvider><AuthenticatedAnalyticsPage /></AuthProvider>);
    expect(await screen.findByText("Events processed per minute")).toBeInTheDocument();
    expect(screen.getByText("Terminal workflows")).toBeInTheDocument();
    expect(screen.getByText("66.7%")).toBeInTheDocument();
    expect(screen.getByText("PostgreSQL current-state report")).toBeInTheDocument();
    expect(analyticsService.lifecycle).toHaveBeenCalledWith(expect.objectContaining({ date_from: expect.any(String), date_to: expect.any(String) }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Analytics time range" }), "30");
    await waitFor(() => expect(analyticsService.lifecycle).toHaveBeenCalledWith(expect.objectContaining({ date_from: expect.any(String), date_to: expect.any(String) })));
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(analyticsService.lifecycle).toHaveBeenCalledTimes(3));
  });

  it("explains when an analytics report is forbidden", async () => {
    vi.spyOn(analyticsService, "lifecycle").mockRejectedValue(new ApiRequestError("Access denied", { status: 403, code: "PERMISSION_DENIED" }));
    renderComponent(<AuthProvider><AuthenticatedAnalyticsPage /></AuthProvider>);
    expect(await screen.findByText("Analytics unavailable")).toBeInTheDocument();
    expect(screen.getByText(/cannot access the requested analytics report/)).toBeInTheDocument();
  });

  it("renders safe API error messaging without stack details", () => {
    const error = new ApiRequestError("The API denied this request. Check the client permissions and endpoint access.", { status: 403, code: "PERMISSION_DENIED", requestId: "request-safe" });
    expect(apiErrorMessage(error)).toContain("request-safe");
    expect(apiErrorMessage(error)).not.toMatch(/stack|Traceback|at Axios/i);
  });

  it("renders reusable loading and empty states", () => {
    renderComponent(<><LoadingState label="Loading workflow details" /><EmptyState title="Nothing here" description="No workflow records." /></>);
    expect(screen.getByText("Loading workflow details")).toBeInTheDocument();
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByText("No workflow records.")).toBeInTheDocument();
  });
});
