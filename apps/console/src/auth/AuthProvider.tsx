import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, setUnauthenticatedHandler } from '../api/client';
import { ApiError, type Staff } from '../api/types';
import { AuthContext, type AuthState } from './context';

const STAFF_KEY = 'sabi.console.staff';

/**
 * Holds the operator session for the console. The session itself is the
 * HttpOnly cookie set by C-039; this provider mirrors the staff identity for
 * the shell (role gating, operator menu) and clears it on C-040.
 *
 * The cookie is the authority, so the mirrored identity is a display hint only
 * and must be confirmed against the server on mount. Trusting the mirror alone
 * shows an operator as signed in after the cookie has expired or been cleared,
 * and every call then fails with a bare 401 that never signs them out.
 */
export function AuthProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const [staff, setStaff] = useState<Staff | null>(null);
  const [status, setStatus] = useState<AuthState['status']>('checking');

  const clear = useCallback(() => {
    setStaff(null);
    setStatus('anonymous');
    try {
      sessionStorage.removeItem(STAFF_KEY);
    } catch {
      // storage may be unavailable; the cookie still governs
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    // A 401 anywhere signs the operator out once, cleanly.
    setUnauthenticatedHandler(() => {
      if (!cancelled) clear();
    });
    // Confirm the cookie with the server; the stashed identity is only a hint.
    api
      .session()
      .then((current) => {
        if (cancelled) return;
        setStaff(current);
        setStatus('authenticated');
        try {
          sessionStorage.setItem(STAFF_KEY, JSON.stringify(current));
        } catch {
          // ignore
        }
      })
      .catch(() => {
        if (!cancelled) clear();
      });
    return () => {
      cancelled = true;
      setUnauthenticatedHandler(undefined);
    };
  }, [clear]);

  const login = useCallback((next: Staff) => {
    setStaff(next);
    setStatus('authenticated');
    try {
      sessionStorage.setItem(STAFF_KEY, JSON.stringify(next));
    } catch {
      // storage may be unavailable; the cookie still governs
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch (err) {
      // A 401 on logout still means the local session is finished.
      if (!(err instanceof ApiError) || err.status !== 401) throw err;
    } finally {
      clear();
    }
  }, [clear]);

  const value = useMemo<AuthState>(
    () => ({ staff, status, login, logout, clear }),
    [staff, status, login, logout, clear],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
