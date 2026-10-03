import { useEffect, useMemo, type ReactNode } from 'react';
import { ConsoleDataContext, type ConsoleData } from './context';
import { createLiveData } from './liveData';
import { createMockData } from './mockData';

/**
 * Selects the data implementation. Demo mode is enabled by `?demo=1` or the
 * `VITE_CONSOLE_DEMO` build flag so the console can be toured without a
 * backend; otherwise it calls the `/v1` gateway.
 */
export function ConsoleDataProvider({ children }: { children: ReactNode }): JSX.Element {
  const demo = useMemo(isDemoMode, []);

  const value = useMemo<ConsoleData>(
    () => (demo ? createMockData() : createLiveData()),
    [demo],
  );

  useEffect(() => {
    if (demo) document.body.dataset.demo = 'true';
    return () => {
      delete document.body.dataset.demo;
    };
  }, [demo]);

  return <ConsoleDataContext.Provider value={value}>{children}</ConsoleDataContext.Provider>;
}

function isDemoMode(): boolean {
  if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('demo')) {
    return true;
  }
  return import.meta.env.VITE_CONSOLE_DEMO === '1';
}
