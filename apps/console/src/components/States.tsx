import type { ReactNode } from 'react';

/**
 * Shared state surfaces. Every view renders these for its loading, empty,
 * error, and offline states so the console is consistent and colour is never
 * the only signal (each state carries an icon and a text label).
 */

export function LoadingState({ label = 'Loading' }: { label?: string }): JSX.Element {
  return (
    <div className="state-block" role="status" aria-live="polite">
      <div className="skeleton" style={{ width: '60%', height: 'var(--row-height)' }} />
      <div className="skeleton" style={{ width: '45%', height: 'var(--row-height)' }} />
      <span className="type-body-small">{label}…</span>
    </div>
  );
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: ReactNode;
}): JSX.Element {
  return (
    <div className="state-block">
      <span aria-hidden="true" className="type-h1">
        ⌸
      </span>
      <h2 className="type-h3">{title}</h2>
      <p className="type-body" style={{ maxWidth: 420 }}>
        {message}
      </p>
      {action}
    </div>
  );
}

export function ErrorState({
  title = 'Something went wrong',
  error,
  onRetry,
}: {
  title?: string;
  error: { message: string } | null;
  onRetry: () => void;
}): JSX.Element {
  return (
    <div className="state-block" role="alert">
      <span aria-hidden="true" className="type-h1">
        ⚠
      </span>
      <h2 className="type-h3">{title}</h2>
      <p className="type-body" style={{ maxWidth: 460 }}>
        {error?.message ?? 'The request failed.'}
      </p>
      <button type="button" className="btn btn-secondary" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}

export function OfflineState({ onRetry }: { onRetry?: () => void }): JSX.Element {
  return (
    <div className="state-block" role="alert">
      <span aria-hidden="true" className="type-h1">
        ⚡
      </span>
      <h2 className="type-h3">You are offline</h2>
      <p className="type-body" style={{ maxWidth: 460 }}>
        The console needs a connection to reach the operator API. Your session is
        unchanged; reconnect to continue.
      </p>
      {onRetry ? (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </div>
  );
}
