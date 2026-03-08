"use client";
import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { auth, User, setAccessToken } from "@/lib/api";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setUser: (u: User | null) => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // On mount: try to restore session. apiFetch auto-handles 401 → tryRefresh internally.
    auth.me()
      .then(setUser)
      .catch(() => { setUser(null); })
      .finally(() => setLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    await auth.login(email, password);
    const me = await auth.me();
    setUser(me);
  };

  const logout = async () => {
    await auth.logout().catch(() => {});
    setAccessToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}
