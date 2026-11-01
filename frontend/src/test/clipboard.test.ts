import { afterEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { copyToClipboard } from "../lib/clipboard";

describe("copyToClipboard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("reports success when the browser copies the value", async () => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    const success = vi.spyOn(toast, "success").mockImplementation(() => "toast-id");

    await expect(copyToClipboard("event-123", "Event ID copied.")).resolves.toBe(true);
    expect(success).toHaveBeenCalledWith("Event ID copied.");
  });

  it("handles a rejected clipboard write without leaking a rejected promise", async () => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error("permission denied")) },
    });
    const error = vi.spyOn(toast, "error").mockImplementation(() => "toast-id");

    await expect(copyToClipboard("event-123", "Event ID copied.")).resolves.toBe(false);
    expect(error).toHaveBeenCalledWith("Clipboard access is unavailable.");
  });
});
