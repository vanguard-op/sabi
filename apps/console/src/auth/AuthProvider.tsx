import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { ApiError, type Staff } from '../api/types';
import { AuthContext, type AuthState } from './context';

const STAFF_KEY = 'sabi.console.staff';

/**
 * Holds the operator session for the console. The session itself is the
 * HttpOnly cookie set by C-039; this provider mirrors the staff identity for
 * the shell (role gating, operator menu) and clears it on C-040.
 */
export function AuthProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const [staff, setStaff] = useState<Staff | null>(null);
  const [status, setStatus] = useState<AuthState['status']>('checking');

  useEffect(() => {
    // A staff identity stashed for the tab is a display hint only; the cookie is
    // the authority. Without it the console is anonymous.
    try {
      const raw = sessionStorage.getItem(STAFF_KEY);
      if (raw) {
        setStaff(JSON.parse(raw) as Staff);
        setStatus('authenticated');
        return;
      }
    } catch {
      // ignore malformed storage
    }
    setStatus('anonymous');
  }, []);

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
      setStaff(null);
      setStatus('anonymous');
      try {
        sessionStorage.removeItem(STAFF_KEY);
      } catch {
        // ignore
      }
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({ staff, status, login, logout }),
    [staff, status, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
