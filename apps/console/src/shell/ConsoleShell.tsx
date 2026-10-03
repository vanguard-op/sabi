import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/context';
import { useOnline, useMediaQuery } from '../hooks/useAsync';
import { layout } from '../theme/tokens';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { UnsupportedWidth } from './UnsupportedWidth';

/** Redirects an unauthenticated operator to the staff login. */
export function RequireAuth(): JSX.Element {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'checking') {
    return (
      <div className="state-block" role="status">
        <span className="type-body-small">Checking your session…</span>
      </div>
    );
  }
  if (status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

/** True when the viewport is at or above the console's supported minimum. */
export function useSupportedWidth(): boolean {
  return useMediaQuery(`(min-width: ${layout.shellMin}px)`);
}

/** True when the sidebar is collapsed: at or above `shell-min`, below `bp-console-md`. */
export function useCollapsedSidebar(): boolean {
  return useMediaQuery(
    `(min-width: ${layout.shellMin}px) and (max-width: ${layout.bpConsoleMd - 1}px)`,
  );
}

/**
 * The console shell: persistent sidebar, top bar, and offline banner.
 *
 * Breakpoint behaviour follows branding.md's Desktop and Staff Console Token
 * Set — at or above `bp-console-md` (1440px) the sidebar is expanded and the
 * content shows its detail panel; from `shell-min` (1024px) up to
 * `bp-console-md` the sidebar collapses to icons and the content is a single
 * column; below `shell-min` the console is unsupported and shows a clear
 * unsupported-width state rather than reflowing to a broken layout.
 */
export function ConsoleShell(): JSX.Element {
  const online = useOnline();
  const supported = useSupportedWidth();
  const collapsed = useCollapsedSidebar();

  if (!supported) {
    return <UnsupportedWidth />;
  }

  return (
    <div className="app-shell stack" style={{ minHeight: '100vh' }}>
      <Topbar />
      {!online ? (
        <div className="offline-banner" role="status" aria-live="polite">
          <span aria-hidden="true">⚡</span>
          <span>
            You are offline. Actions are unavailable until the connection returns.
          </span>
        </div>
      ) : null}
      <div className="row" style={{ alignItems: 'stretch', flex: 1, minHeight: 0 }}>
        <Sidebar collapsed={collapsed} />
        <main className="grow" style={{ minWidth: 0 }}>
          <div className="content">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
