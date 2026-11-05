import { useCallback, useEffect, useMemo, useState } from 'react';
import { authApi } from '../utils/api.js';
import { AuthContext } from './auth.js';

const STORAGE_KEY = 'covid-dashboard-session';

function readStoredSession() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw);
    if (parsed?.token && parsed?.user) return parsed;
  } catch {
    // Sesión corrupta: se ignora y se solicita login de nuevo.
  }
  return null;
}

function persistSession(session) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Si el navegador bloquea localStorage, la sesión vive solo en memoria.
  }
}

function clearSession() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Sin acción.
  }
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(readStoredSession);
  const [initialToken] = useState(() => readStoredSession()?.token ?? null);
  const [loading, setLoading] = useState(Boolean(initialToken));

  useEffect(() => {
    if (!initialToken) return undefined;

    const controller = new AbortController();

    authApi
      .me(initialToken, controller.signal)
      .then((user) => {
        if (controller.signal.aborted) return;
        setSession((current) => {
          if (!current?.token) return current;
          const next = { token: current.token, user };
          persistSession(next);
          return next;
        });
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        clearSession();
        setSession(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [initialToken]);

  const login = useCallback(async (credentials) => {
    const data = await authApi.login(credentials);
    const next = { token: data.access_token, user: data.user };
    persistSession(next);
    setSession(next);
    return data.user;
  }, []);

  const register = useCallback(async (payload) => {
    const data = await authApi.register(payload);
    const next = { token: data.access_token, user: data.user };
    persistSession(next);
    setSession(next);
    return data.user;
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setSession(null);
  }, []);

  const value = useMemo(
    () => ({
      user: session?.user ?? null,
      token: session?.token ?? null,
      isAuthenticated: Boolean(session?.token),
      loading,
      login,
      register,
      logout,
    }),
    [session, loading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
