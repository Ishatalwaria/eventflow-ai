import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { clearApiToken, getApiToken, setApiToken } from "../api/auth-token";
import { authService } from "../api/services/auth";
import type { UserProfile } from "../api/types";

interface AuthContextValue {
  user: UserProfile | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isStaff: boolean;
  token: string;
  hasToken: boolean;
  setToken: (value: string) => void;
  clearToken: () => void;
  login: (credentials: { email: string; password: string }) => Promise<void>;
  register: (payload: {
    name: string;
    email: string;
    password: string;
    password_confirm: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [token, setTokenValue] = useState(() => getApiToken() || "");

  const refreshUser = useCallback(async () => {
    try {
      const profile = await authService.getCurrentUser();
      setUser(profile);
    } catch {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const setToken = useCallback((value: string) => {
    const normalized = value.trim();
    if (normalized !== token) queryClient.clear();
    setApiToken(normalized || null);
    setTokenValue(normalized);
  }, [token, queryClient]);

  const clearToken = useCallback(() => setToken(""), [setToken]);

  const login = useCallback(
    async (credentials: { email: string; password: string }) => {
      await authService.login(credentials);
      queryClient.clear();
      await refreshUser();
    },
    [queryClient, refreshUser]
  );

  const register = useCallback(
    async (payload: {
      name: string;
      email: string;
      password: string;
      password_confirm: string;
    }) => {
      await authService.register(payload);
      queryClient.clear();
      await refreshUser();
    },
    [queryClient, refreshUser]
  );

  const logout = useCallback(async () => {
    try {
      await authService.logout();
    } catch {
      // ignore network errors on logout
    } finally {
      setUser(null);
      clearApiToken();
      setTokenValue("");
      queryClient.clear();
    }
  }, [queryClient]);

  useEffect(() => {
    const onUnauthorized = () => {
      setUser(null);
      clearApiToken();
      setTokenValue("");
      queryClient.clear();
    };
    window.addEventListener("eventflow:unauthorized", onUnauthorized);
    return () => window.removeEventListener("eventflow:unauthorized", onUnauthorized);
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      isAuthenticated: Boolean(user),
      isStaff: Boolean(user?.is_staff),
      token,
      hasToken: Boolean(user) || Boolean(token),
      setToken,
      clearToken,
      login,
      register,
      logout,
      refreshUser,
    }),
    [user, isLoading, token, setToken, clearToken, login, register, logout, refreshUser]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
