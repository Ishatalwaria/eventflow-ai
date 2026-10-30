import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError, apiErrorMessage } from "../api/client";
import { eventsService } from "../api/services/events";
import { healthService } from "../api/services/health";
import { incidentsService } from "../api/services/incidents";
import { workflowsService } from "../api/services/workflows";
import { AnalyticsPage } from "../features/analytics/AnalyticsPage";
import { EmptyState, LoadingState } from "../components/layout";
import { eventDetailFixture, failedWorkflowFixture, incidentSummaryFixture } from "./fixtures";
import { renderApp, renderComponent } from "./render";

beforeEach(() => {
  vi.spyOn(eventsService, "get").mockResolvedValue(eventDetailFixture);
  vi.spyOn(eventsService, "create").mockResolvedValue({ event_id: eventDetailFixture.id, workflow_id: failedWorkflowFixture.id, workflow_state: "RECEIVED", duplicate: false });
  vi.spyOn(workflowsService, "get").mockResolvedValue(failedWorkflowFixture);
  vi.spyOn(incidentsService, "createSummary").mockResolvedValue(incidentSummaryFixture);
  vi.spyOn(healthService, "live").mockResolvedValue({ status: "ok" });
  vi.spyOn(healthService, "ready").mockResolvedValue({ status: "ready", checks: { database: "ok" } });
});

describe("EventFlow frontend integration", () => {
  it("navigates between application sections", async () => {
    const user = userEvent.setup();
    renderApp("/events", "");
    expect(await screen.findByText("API connection required")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Settings" }));
    expect(await screen.findByText("Backend connection")).toBeInTheDocument();
  });

  it("renders backend event details in the session event table", async () => {
    sessionStorage.setItem("eventflow.submittedEvents.CLIENT-TEST", JSON.stringify([{ event_id: eventDetailFixture.id, workflow_id: failedWorkflowFixture.id, workflow_state: "FAILED", duplicate: false }]));
    renderApp("/events");
    expect(await screen.findByText("Known events")).toBeInTheDocument();
    expect(await screen.findByText("checkout-web")).toBeInTheDocument();
    expect(screen.getByText("idempotency-001")).toBeInTheDocument();
    expect(eventsService.get).toHaveBeenCalledWith(eventDetailFixture.id);
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

  it("shows the explicit unavailable analytics state without fabricated charts", () => {
    renderComponent(<AnalyticsPage />);
    expect(screen.getByText("No browser-facing analytics endpoint")).toBeInTheDocument();
    expect(screen.getByText("Events processed per minute")).toBeInTheDocument();
    expect(screen.getAllByText("Not Available").length).toBeGreaterThan(0);
    expect(screen.queryByRole("img", { name: /chart/i })).not.toBeInTheDocument();
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
