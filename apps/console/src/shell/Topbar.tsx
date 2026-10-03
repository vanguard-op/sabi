import { useNavigate } from 'react-router-dom';
import { ROLE_LABELS, useAuth } from '../auth/context';
import { useTheme } from '../theme/ThemeProvider';

export function Topbar(): JSX.Element {
  const { staff, logout } = useAuth();
  const { mode, toggle } = useTheme();
  const navigate = useNavigate();

  async function onLogout() {
    await logout();
    navigate('/login', { replace: true });
  }

  return (
    <header className="topbar">
      <div className="row gap-sm">
        <span className="type-h3">Sabi</span>
        <span aria-hidden="true" className="text-secondary">
          /
        </span>
        <span className="type-body-small text-secondary">Operations Console</span>
      </div>
      <div className="row gap-sm">
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={toggle}
          aria-label={`Switch to ${mode === 'light' ? 'dark' : 'light'} theme`}
        >
          {mode === 'light' ? 'Dark' : 'Light'}
        </button>
        {staff ? (
          <>
            <div className="stack" style={{ textAlign: 'right' }}>
              <span className="type-body-small" style={{ fontWeight: 600 }}>
                {staff.email}
              </span>
              <span className="type-caption text-secondary">{ROLE_LABELS[staff.role]}</span>
            </div>
            <button type="button" className="btn btn-outline btn-sm" onClick={onLogout}>
              Sign out
            </button>
          </>
        ) : null}
      </div>
    </header>
  );
}
