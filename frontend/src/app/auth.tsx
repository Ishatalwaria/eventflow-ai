import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { clearApiToken, setApiToken } from "../api/auth-token";

interface AuthContextValue {
  token: string;
  setToken: (value: string) => void;
  clearToken: () => void;
  hasToken: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [token, setTokenValue] = useState("");
  const setToken = (value: string) => {
    const normalized = value.trim();
    if (normalized !== token) queryClient.clear();
    setApiToken(normalized || null);
    setTokenValue(normalized);
  };
  const clearToken = () => setToken("");
  useEffect(() => {
    const onUnauthorized = () => {
      clearApiToken();
      setTokenValue("");
      queryClient.clear();
    };
    window.addEventListener("eventflow:unauthorized", onUnauthorized);
    return () => window.removeEventListener("eventflow:unauthorized", onUnauthorized);
  }, [queryClient]);
  const value = useMemo(() => ({ token, setToken, clearToken, hasToken: Boolean(token) }), [token, queryClient]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
