import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { cssVariables, palettes, type ThemeMode } from './tokens';

interface ThemeState {
  mode: ThemeMode;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeState | null>(null);

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider');
  return ctx;
}

const STORAGE_KEY = 'sabi.console.theme';

function initialMode(): ThemeMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    // storage unavailable
  }
  if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }
  return 'light';
}

/**
 * Applies the Desktop and Staff Console token set as CSS custom properties on
 * the document root, switching between the light and dark palettes. This is the
 * console's token source; call sites read `var(--...)` only.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const [mode, setMode] = useState<ThemeMode>(initialMode);

  const toggle = useCallback(() => {
    setMode((m) => (m === 'light' ? 'dark' : 'light'));
  }, []);

  useEffect(() => {
    const vars = cssVariables(palettes[mode]);
    const root = document.documentElement;
    for (const [key, value] of Object.entries(vars)) {
      root.style.setProperty(key, String(value));
    }
    root.dataset.theme = mode;
    root.style.colorScheme = mode;
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // ignore
    }
  }, [mode]);

  const value = useMemo(() => ({ mode, toggle }), [mode, toggle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
