import { useEffect, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider, useAuth } from "../app/auth";
import App from "../App";

import { clearApiToken, setApiToken } from "../api/auth-token";

function SetTestToken({ token }: { token: string }) {
  const auth = useAuth();
  useEffect(() => { if (token) auth.setToken(token); }, [auth, token]);
  return null;
}

export function renderApp(path: string, token = "CLIENT-TEST.secret") {
  if (token) setApiToken(token);
  else clearApiToken();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><AuthProvider><SetTestToken token={token} /><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></AuthProvider></QueryClientProvider>);
}

export function renderComponent(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}
