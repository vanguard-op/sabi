import type { ReactNode } from 'react';

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}): JSX.Element {
  return (
    <div className="page-header row between gap-md wrap" style={{ alignItems: 'flex-end' }}>
      <div className="stack gap-xs" style={{ maxWidth: 720 }}>
        <h1 className="type-h1">{title}</h1>
        {description ? <p className="type-body text-secondary">{description}</p> : null}
      </div>
      {actions ? <div className="row gap-sm wrap">{actions}</div> : null}
    </div>
  );
}

/** A surface-level permission notice for a role that may not view the page. */
export function ForbiddenState(): JSX.Element {
  return (
    <div className="state-block" role="alert">
      <span aria-hidden="true" className="type-h1">
        ⛔
      </span>
      <h2 className="type-h3">Not available for your role</h2>
      <p className="type-body" style={{ maxWidth: 460 }}>
        Your operator role does not grant access to this surface. Ask an
        administrator if you need it.
      </p>
    </div>
  );
}
