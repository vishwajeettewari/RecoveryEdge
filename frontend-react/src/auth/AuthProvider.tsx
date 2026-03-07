import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { apiFetch, clearToken, storeToken } from "../api/client";
import { defaultLandingForRole, hasRolePermission, type Permission } from "./roles";

export interface AuthUser {
  id: string;
  username: string;
  full_name?: string | null;
  email?: string | null;
  role: string;
  is_active: boolean;
  created_at?: number;
  last_login_at?: number | null;
}

interface AuthMeResponse {
  user: AuthUser;
  role: string;
  permissions: string[];
}

interface AuthContextValue {
  user: AuthUser | null;
  role: string;
  permissions: string[];
  loading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  hasPermission: (permission: Permission | string) => boolean;
  defaultLanding: string;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await apiFetch<AuthMeResponse>("/api/auth/me");
      setUser(me.user);
      setPermissions(me.permissions || []);
    } catch {
      setUser(null);
      setPermissions([]);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        await refresh();
      } finally {
        if (alive) {
          setLoading(false);
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [refresh]);

  const login = useCallback(
    async (username: string, password: string) => {
      const out = await apiFetch<{ access_token?: string }>("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (out.access_token) {
        storeToken(out.access_token);
      }
      await refresh();
    },
    [refresh]
  );

  const logout = useCallback(async () => {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } finally {
      clearToken();
      setUser(null);
      setPermissions([]);
    }
  }, []);

  const role = user?.role || "";
  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      role,
      permissions,
      loading,
      isAuthenticated: !!user,
      login,
      logout,
      refresh,
      hasPermission: (permission) => permissions.includes(permission) || hasRolePermission(role, permission as Permission),
      defaultLanding: defaultLandingForRole(role),
    }),
    [user, role, permissions, loading, login, logout, refresh]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
