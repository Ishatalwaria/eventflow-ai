import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { healthService } from "../api/services/health";
import { renderApp } from "./render";

describe("system health", () => {
  beforeEach(() => {
    vi.spyOn(healthService, "live").mockResolvedValue({ status: "ok" });
    vi.spyOn(healthService, "ready").mockResolvedValue({ status: "ready", checks: { database: "ok" } });
  });

  it("shows only endpoint-backed health and marks unmonitored services unavailable", async () => {
    renderApp("/health", "");
    expect(await screen.findByText("Django API")).toBeInTheDocument();
    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.getAllByText("Not Available").length).toBeGreaterThanOrEqual(5);
    expect(screen.getByText(/separate metrics credential/)).toBeInTheDocument();
  });
});
