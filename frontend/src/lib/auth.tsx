"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "@/lib/api";

type AuthState = {
  token: string | null;
  email: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const saved = localStorage.getItem("dmidop_token");
    if (!saved) {
      setLoading(false);
      return;
    }
    api
      .me(saved)
      .then((u) => {
        setToken(saved);
        setEmail(u.email);
      })
      .catch(() => localStorage.removeItem("dmidop_token"))
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      token,
      email,
      loading,
      async login(em, password) {
        const res = await api.login(em, password);
        localStorage.setItem("dmidop_token", res.access_token);
        setToken(res.access_token);
        const me = await api.me(res.access_token);
        setEmail(me.email);
      },
      logout() {
        localStorage.removeItem("dmidop_token");
        setToken(null);
        setEmail(null);
      },
    }),
    [token, email, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth requires AuthProvider");
  return ctx;
}
