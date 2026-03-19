"use client";
import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { auth, User, setAccessToken, onSessionExpired } from "@/lib/api";

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

  const handleSessionExpired = useCallback(() => {
    setAccessToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    onSessionExpired(handleSessionExpired);
    return () => onSessionExpired(null);
  }, [handleSessionExpired]);

  useEffect(() => {
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
