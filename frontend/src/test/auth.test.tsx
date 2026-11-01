import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { authService } from "../api/services/auth";
import { LoginPage } from "../features/auth/LoginPage";
import { SignupPage } from "../features/auth/SignupPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { renderComponent } from "./render";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../app/auth";

describe("Authentication & Access Control Frontend", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders login form and invokes authService on submit", async () => {
    const loginSpy = vi.spyOn(authService, "login").mockResolvedValue({
      id: 1,
      name: "Alice",
      email: "alice@example.com",
      type: "user",
      is_staff: false,
    });
    vi.spyOn(authService, "getCurrentUser").mockResolvedValue({
      id: "1",
      username: "alice@example.com",
      name: "Alice",
      email: "alice@example.com",
      type: "user",
      is_staff: false,
      is_api_client: false,
    });

    renderComponent(
      <MemoryRouter initialEntries={["/login"]}>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>
    );

    expect(screen.getByRole("heading", { name: "Sign in to your account" })).toBeInTheDocument();
    const emailInput = screen.getByPlaceholderText("admin@eventflow.local");
    const passwordInput = screen.getByPlaceholderText("••••••••••••");

    await userEvent.type(emailInput, "alice@example.com");
    await userEvent.type(passwordInput, "ValidPassword123!");
    await userEvent.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => {
      expect(loginSpy).toHaveBeenCalledWith({
        email: "alice@example.com",
        password: "ValidPassword123!",
      });
    });
  });

  it("renders signup form and rejects mismatched passwords before network call", async () => {
    const registerSpy = vi.spyOn(authService, "register");

    renderComponent(
      <MemoryRouter initialEntries={["/signup"]}>
        <AuthProvider>
          <SignupPage />
        </AuthProvider>
      </MemoryRouter>
    );

    expect(screen.getByRole("heading", { name: "Create your account & workspace" })).toBeInTheDocument();

    await userEvent.type(screen.getByPlaceholderText("Jane Doe"), "Alice");
    await userEvent.type(screen.getByPlaceholderText("jane@company.com"), "alice@example.com");
    await userEvent.type(screen.getByPlaceholderText("Minimum 8 characters"), "Password123!");
    await userEvent.type(screen.getByPlaceholderText("Re-enter password"), "MismatchPassword123!");

    await userEvent.click(screen.getByRole("button", { name: "Create Account & Workspace" }));

    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();
    expect(registerSpy).not.toHaveBeenCalled();
  });

  it("renders user profile and API client keys on Settings page", async () => {
    vi.spyOn(authService, "getCurrentUser").mockResolvedValue({
      id: "1",
      username: "alice@example.com",
      name: "Alice Smith",
      email: "alice@example.com",
      type: "user",
      is_staff: false,
      is_api_client: false,
    });
    vi.spyOn(authService, "listClients").mockResolvedValue({
      count: 1,
      results: [
        {
          id: "11111111-2222-3333-4444-555555555555",
          name: "alice-prod-key",
          can_view_analytics: false,
          created_at: "2026-11-01T12:00:00Z",
          rotated_at: null,
          revoked_at: null,
          is_active: true,
        },
      ],
    });

    renderComponent(
      <MemoryRouter initialEntries={["/settings"]}>
        <AuthProvider>
          <SettingsPage />
        </AuthProvider>
      </MemoryRouter>
    );

    expect(await screen.findByText("User Profile")).toBeInTheDocument();
    expect(await screen.findByText("Alice Smith")).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(await screen.findByText("alice-prod-key")).toBeInTheDocument();
    expect(screen.getByText(/ID: 11111111-2222-3333-4444-555555555555/)).toBeInTheDocument();
  });
});
