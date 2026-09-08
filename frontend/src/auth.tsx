import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { apiClient, setToken, getToken } from "./api/client";
import type { Me } from "./api/types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthCtx = createContext<AuthState>({
  me: null,
  loading: true,
  login: async () => undefined,
  logout: async () => undefined,
  refresh: async () => undefined,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    // Don't even try /me if there's no token - avoids spurious 401s.
    if (!getToken()) {
      setMe(null);
      setLoading(false);
      return;
    }
    try {
      const m = await apiClient.me();
      setMe(m);
    } catch {
      // Clear the stale/invalid token silently.
      setToken(null);
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, []);

  const login = async (username: string, password: string) => {
    const res = await apiClient.login(username, password);
    setToken(res.access_token);
    const m = await apiClient.me();
    setMe(m);
  };

  const logout = async () => {
    try {
      await apiClient.logout();
    } catch {
      /* noop */
    }
    setToken(null);
    setMe(null);
  };

  return (
    <AuthCtx.Provider value={{ me, loading, login, logout, refresh }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  return useContext(AuthCtx);
}
