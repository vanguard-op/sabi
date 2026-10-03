import { useCallback, useMemo, useState, type FormEvent } from 'react';
import type { AuditEntry, AuditFinding, AuditQuery, ExportRequest } from '../api/types';
import { canCloseFinding, canExportAudit, canReviewAudit, useAuth } from '../auth/context';
import { DataTable, type Column } from '../components/DataTable';
import { Field } from '../components/Field';
import { Modal } from '../components/Modal';
import { ForbiddenState, PageHeader } from '../components/Page';
import { EmptyState, ErrorState, LoadingState } from '../components/States';
import { useData } from '../data/context';
import { useAsync, useOnline } from '../hooks/useAsync';
import { formatDateTime } from '../lib/format';

/** High-risk actions the audit view flags (operations-console.md). */
const HIGH_RISK = new Set([
  'role.grant',
  'role.revoke',
  'access.break_glass',
  'capability.quarantine',
  'refund.above_limit',
  'audit.export',
]);

function isHighRisk(entry: AuditEntry): boolean {
  return HIGH_RISK.has(entry.action) || entry.action.startsWith('role.');
}

function humanAction(action: string): string {
  return action.replace(/[._]/g, ' ');
}

export function AuditPage(): JSX.Element {
  const { staff } = useAuth();
  const data = useData();
  const online = useOnline();
  const [filters, setFilters] = useState<AuditQuery>({});
  const [applied, setApplied] = useState<AuditQuery>({});
  const [exportOpen, setExportOpen] = useState(false);
  const [closing, setClosing] = useState<AuditFinding | null>(null);
  const [selectedId, setSelectedId] = useState<string | undefined>();

  const audit = useAsync(() => data.listAudit(applied), [applied, data]);
  const findings = useAsync(() => data.listFindings(), [data]);
  const [exportNotice, setExportNotice] = useState<string | null>(null);

  const entries = audit.data?.entries ?? [];
  const openFindings = useMemo(
    () => (findings.data ?? []).filter((f) => f.status === 'open'),
    [findings.data],
  );

  const columns = useMemo<Column<AuditEntry>[]>(
    () => [
      {
        key: 'occurredAt',
        header: 'When',
        render: (e) => formatDateTime(e.occurredAt),
        sortValue: (e) => e.occurredAt,
      },
      {
        key: 'actor',
        header: 'Actor',
        render: (e) => (
          <div className="stack">
            <span style={{ fontWeight: 600 }}>{e.actor}</span>
            <span className="type-caption text-secondary">{e.role}</span>
          </div>
        ),
      },
      {
        key: 'action',
        header: 'Action',
        render: (e) => (
          <div className="row gap-xs">
            {isHighRisk(e) ? (
              <span className="badge badge-warning">
                <span aria-hidden="true">!</span>
                High risk
              </span>
            ) : null}
            <span>{humanAction(e.action)}</span>
          </div>
        ),
      },
      {
        key: 'target',
        header: 'Target',
        render: (e) => <span className="type-mono">{e.target}</span>,
      },
      {
        key: 'reason',
        header: 'Reason',
        render: (e) => <span className="text-secondary">{e.reason ?? '—'}</span>,
      },
    ],
    [],
  );

  if (!canReviewAudit(staff?.role)) return <ForbiddenState />;

  function applyFilters(e: FormEvent) {
    e.preventDefault();
    setApplied({ ...filters });
  }

  function clearFilters() {
    setFilters({});
    setApplied({});
  }

  return (
    <>
      <PageHeader
        title="Privileged-action audit view"
        description="Review privileged actions and confirm every operator action has a matching audit entry. This view reads the tamper-evident log; it never writes to it."
        actions={
          canExportAudit(staff?.role) ? (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => setExportOpen(true)}
              disabled={!online}
            >
              Export extract
            </button>
          ) : undefined
        }
      />

      {!online ? (
        <div className="alert alert-warning" role="status" style={{ marginBottom: 'var(--space-md)' }}>
          <span aria-hidden="true">⚡</span>
          <span>Offline: the audit log and export are unavailable.</span>
        </div>
      ) : null}

      {exportNotice ? (
        <div className="alert alert-info" role="status" style={{ marginBottom: 'var(--space-md)' }}>
          <span aria-hidden="true">i</span>
          <span>{exportNotice}</span>
        </div>
      ) : null}

      <form className="toolbar" onSubmit={applyFilters}>
        <div className="field">
          <label className="field-label" htmlFor="filter-actor">
            Actor
          </label>
          <input
            id="filter-actor"
            className="input"
            value={filters.actor ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, actor: e.target.value }))}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="filter-role">
            Role
          </label>
          <input
            id="filter-role"
            className="input"
            value={filters.role ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, role: e.target.value }))}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="filter-target">
            Target
          </label>
          <input
            id="filter-target"
            className="input"
            value={filters.target ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, target: e.target.value }))}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="filter-action">
            Action
          </label>
          <input
            id="filter-action"
            className="input"
            value={filters.action ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, action: e.target.value }))}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="filter-from">
            From
          </label>
          <input
            id="filter-from"
            className="input"
            type="date"
            value={filters.from ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, from: e.target.value }))}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="filter-to">
            To
          </label>
          <input
            id="filter-to"
            className="input"
            type="date"
            value={filters.to ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, to: e.target.value }))}
          />
        </div>
        <button type="submit" className="btn btn-secondary">
          Apply
        </button>
        <button type="button" className="btn btn-ghost" onClick={clearFilters}>
          Clear
        </button>
      </form>

      <div className="split">
        <div>
          {audit.status === 'loading' ? <LoadingState label="Loading audit entries" /> : null}
          {audit.status === 'error' ? (
            <ErrorState error={audit.error} onRetry={audit.reload} />
          ) : null}
          {audit.status === 'success' && entries.length === 0 ? (
            <EmptyState
              title="No audit entries match"
              message="Clear the filters or widen the date range to see privileged actions."
            />
          ) : null}
          {audit.status === 'success' && entries.length > 0 ? (
            <DataTable
              caption="Privileged actions"
              columns={columns}
              rows={entries}
              getRowId={(e) => e.auditId}
              selectedId={selectedId}
              onSelect={(e) => setSelectedId(e.auditId)}
            />
          ) : null}
        </div>

        <aside className="card">
          <div className="row between gap-sm" style={{ marginBottom: 'var(--space-md)' }}>
            <h2 className="type-h3">Findings</h2>
            {openFindings.length > 0 ? (
              <span className="badge badge-warning">
                <span aria-hidden="true">!</span>
                {openFindings.length} open
              </span>
            ) : null}
          </div>
          {findings.status === 'loading' ? <LoadingState label="Loading findings" /> : null}
          {findings.status === 'error' ? (
            <ErrorState error={findings.error} onRetry={findings.reload} />
          ) : null}
          {findings.status === 'success' && (findings.data ?? []).length === 0 ? (
            <p className="type-body-small text-secondary">
              An unlogged action raised during a review appears here to close.
            </p>
          ) : null}
          {findings.status === 'success' ? (
            <ul className="stack gap-sm" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {(findings.data ?? []).map((f) => (
                <li key={f.findingsId} className="panel stack gap-xs">
                  <div className="row between gap-sm">
                    <span className="type-body-small" style={{ fontWeight: 600 }}>
                      {f.summary}
                    </span>
                    <span className={`badge ${f.status === 'open' ? 'badge-warning' : 'badge-neutral'}`}>
                      {f.status === 'open' ? 'Open' : 'Closed'}
                    </span>
                  </div>
                  <span className="type-caption text-secondary">
                    Opened {formatDateTime(f.openedAt)}
                    {f.closedAt ? ` · Closed ${formatDateTime(f.closedAt)}` : ''}
                  </span>
                  {f.status === 'open' && canCloseFinding(staff?.role) ? (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={!online}
                      onClick={() => setClosing(f)}
                    >
                      Close finding
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </aside>
      </div>

      {exportOpen ? (
        <ExportDialog
          onClose={() => setExportOpen(false)}
          onSubmit={async (body) => {
            const result = await data.exportAudit(body);
            setExportOpen(false);
            setExportNotice(
              `Export ${result.exportId} queued. A bulk export is itself a logged privileged action.`,
            );
          }}
        />
      ) : null}

      {closing ? (
        <CloseFindingDialog
          finding={closing}
          onClose={() => setClosing(null)}
          onSubmit={async (resolution) => {
            await data.closeFinding(closing.findingsId, { resolution });
            setClosing(null);
            findings.reload();
          }}
        />
      ) : null}
    </>
  );
}

function ExportDialog({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (body: ExportRequest) => Promise<void>;
}): JSX.Element {
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [format, setFormat] = useState<ExportRequest['format']>('csv');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!from || !to) {
      setError('Choose a start and end date.');
      return;
    }
    if (to < from) {
      setError('The end date must not precede the start date.');
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit({ from, to, format });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The export could not be queued.');
      setSubmitting(false);
    }
  }

  return (
    <Modal title="Export audit extract" onClose={onClose}>
      <form className="stack gap-md" onSubmit={submit} noValidate>
        <p className="type-body-small text-secondary">
          A bulk export is a privileged action and is logged against your
          operator identity.
        </p>
        <Field label="From" error={error && !from ? error : null}>
          {(props) => (
            <input
              {...props}
              className="input"
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          )}
        </Field>
        <Field label="To" error={error && from && !to ? error : null}>
          {(props) => (
            <input
              {...props}
              className="input"
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          )}
        </Field>
        <Field label="Format">
          {(props) => (
            <select
              {...props}
              className="select"
              value={format}
              onChange={(e) => setFormat(e.target.value as ExportRequest['format'])}
            >
              <option value="csv">CSV</option>
              <option value="json">JSON</option>
            </select>
          )}
        </Field>
        {error && from && to ? (
          <div className="alert alert-error" role="alert">
            <span aria-hidden="true">⚠</span>
            <span>{error}</span>
          </div>
        ) : null}
        <div className="row gap-sm between">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Queueing…' : 'Queue export'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function CloseFindingDialog({
  finding,
  onClose,
  onSubmit,
}: {
  finding: AuditFinding;
  onClose: () => void;
  onSubmit: (resolution: string) => Promise<void>;
}): JSX.Element {
  const [resolution, setResolution] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const submit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      if (!resolution.trim()) {
        setError('Record the resolution.');
        return;
      }
      setError(null);
      setSubmitting(true);
      try {
        await onSubmit(resolution.trim());
        setDone(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'The finding could not be closed.');
        setSubmitting(false);
      }
    },
    [resolution, onSubmit],
  );

  return (
    <Modal title="Close finding" onClose={onClose}>
      {done ? (
        <p className="type-body" role="status">
          Finding closed and the resolution recorded.
        </p>
      ) : (
        <form className="stack gap-md" onSubmit={submit} noValidate>
          <dl className="detail-list">
            <dt>Finding</dt>
            <dd>{finding.summary}</dd>
          </dl>
          <Field label="Resolution" error={error}>
            {(props) => (
              <textarea
                {...props}
                className="textarea"
                value={resolution}
                onChange={(e) => setResolution(e.target.value)}
              />
            )}
          </Field>
          <div className="row gap-sm between">
            <button type="button" className="btn btn-ghost" onClick={onClose} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Closing…' : 'Close finding'}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}
