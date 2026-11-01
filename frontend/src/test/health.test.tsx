import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { healthService } from "../api/services/health";
import { renderApp } from "./render";

describe("system health", () => {
  beforeEach(() => {
    vi.spyOn(healthService, "live").mockResolvedValue({ status: "ok" });
    vi.spyOn(healthService, "ready").mockResolvedValue({ status: "ready", checks: { database: "ok" } });
  });

  it("keeps public API liveness and readiness available before the client connects", async () => {
    renderApp("/health", "");
    expect(await screen.findByText("Connect an API client for service checks")).toBeInTheDocument();
    expect(screen.getByText("Django API")).toBeInTheDocument();
    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.getByText("Public database readiness check")).toBeInTheDocument();
  });

  it("renders authenticated service health and metrics from the API response", async () => {
    vi.spyOn(healthService, "services").mockResolvedValue({
      generated_at: "2026-10-31T12:00:00Z",
      services: [
        { name: "Django API", status: "healthy", last_checked: "2026-10-31T12:00:00Z", detail: "Summary responded." },
        { name: "Kafka", status: "healthy", last_checked: "2026-10-31T12:00:00Z", detail: "Probe succeeded." },
      ],
      metrics: {
        api_requests_total: 12,
        api_average_latency_ms: 24.5,
        worker_attempts_total: 0,
        retry_count: 2,
        dead_letter_count: 0,
        llm_error_count: 0,
        llm_average_latency_ms: null,
        task_queue_depth: 3,
        dead_letter_queue_depth: 0,
        availability: "available",
      },
    });

    renderApp("/health");

    expect(await screen.findByText("Service status")).toBeInTheDocument();
    expect(await screen.findByText("Kafka")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("24.5 ms")).toBeInTheDocument();
    expect(screen.getByText("Worker attempts (24h)")).toBeInTheDocument();
    expect(screen.getByText("Retries (24h)")).toBeInTheDocument();
    expect(screen.getAllByText("0").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Not available").length).toBeGreaterThan(0);
  });

  it("keeps the configured client connected when navigating to System Health", async () => {
    const services = vi.spyOn(healthService, "services").mockResolvedValue({
      generated_at: "2026-10-31T12:00:00Z",
      services: [
        { name: "RabbitMQ", status: "healthy", last_checked: "2026-10-31T12:00:00Z", detail: "Dependency probe succeeded." },
        { name: "Kafka", status: "healthy", last_checked: "2026-10-31T12:00:00Z", detail: "Dependency probe succeeded." },
        { name: "Workflow worker", status: "healthy", last_checked: "2026-10-31T12:00:00Z", detail: "Metrics endpoint responded." },
      ],
      metrics: {
        api_requests_total: null,
        api_average_latency_ms: null,
        worker_attempts_total: null,
        retry_count: null,
        dead_letter_count: null,
        llm_error_count: null,
        llm_average_latency_ms: null,
        task_queue_depth: 0,
        dead_letter_queue_depth: 0,
        availability: "available",
      },
    });
    const user = userEvent.setup();
    renderApp("/settings");

    await user.click(await screen.findByRole("link", { name: "System health" }));

    expect(await screen.findByText("RabbitMQ")).toBeInTheDocument();
    expect(screen.getByText("Kafka")).toBeInTheDocument();
    expect(screen.getByText("Workflow worker")).toBeInTheDocument();
    expect(services).toHaveBeenCalledOnce();
  });
});
