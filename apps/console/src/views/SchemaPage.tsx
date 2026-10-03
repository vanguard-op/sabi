import { useMemo, useState } from 'react';
import type { Capability, ReviewDecision } from '../api/types';
import { canReviewProviders, useAuth } from '../auth/context';
import { CapabilityStatusBadge, HealthStatusBadge } from '../components/Badges';
import { DataTable } from '../components/DataTable';
import { ForbiddenState, PageHeader } from '../components/Page';
import { ReviewDialog } from '../components/ReviewDialog';
import { EmptyState, ErrorState, LoadingState } from '../components/States';
import { useData } from '../data/context';
import { useRegistry } from '../data/useRegistry';
import { formatDateTime } from '../lib/format';
import { useOnline } from '../hooks/useAsync';

interface SchemaRow {
  active: Capability;
  /** A pending version of the same capability, if one is under review. */
  submitted: Capability | null;
}

/**
 * Groups capabilities by their claimed service so the active schema version and
 * a pending replacement sit side by side. The previous version stays active
 * while the new one is under review (operations.md).
 */
function groupByService(capabilities: Capability[]): SchemaRow[] {
  const byService = new Map<string, Capability[]>();
  for (const cap of capabilities) {
    const key = cap.serviceId ?? cap.capabilityId;
    const list = byService.get(key) ?? [];
    list.push(cap);
    byService.set(key, list);
  }
  const rows: SchemaRow[] = [];
  for (const list of byService.values()) {
    const active = list.find((c) => c.status === 'active');
    const pending = list.find((c) => c.status === 'pending');
    if (active && pending) rows.push({ active, submitted: pending });
    else if (pending) rows.push({ active: pending, submitted: null });
    else if (active) rows.push({ active, submitted: null });
  }
  return rows;
}

export function SchemaPage(): JSX.Element {
  const { staff } = useAuth();
  const data = useData();
  const registry = useRegistry();
  const online = useOnline();
  const [modal, setModal] = useState<{ capability: Capability; decision: ReviewDecision } | null>(null);

  const rows = useMemo(() => groupByService(registry.capabilities), [registry.capabilities]);

  if (!canReviewProviders(staff?.role)) return <ForbiddenState />;

  const columns = [
    {
      key: 'service',
      header: 'Capability',
      render: (row: SchemaRow) => (
        <div className="stack">
          <span style={{ fontWeight: 600 }}>{row.active.name}</span>
          <span className="type-caption text-secondary type-mono">
            {row.active.serviceId ?? 'unclaimed service'}
          </span>
        </div>
      ),
    },
    {
      key: 'active',
      header: 'Active version',
      render: (row: SchemaRow) =>
        row.submitted ? (
          <div className="stack gap-xs">
            <span className="type-mono">{row.active.schemaVersion}</span>
            <span className="type-caption text-secondary">
              in use since {formatDateTime(row.active.updatedAt)}
            </span>
          </div>
        ) : (
          <span className="type-mono text-secondary">{row.active.schemaVersion}</span>
        ),
    },
    {
      key: 'submitted',
      header: 'Submitted version',
      render: (row: SchemaRow) =>
        row.submitted ? (
          <div className="stack gap-xs">
            <span className="type-mono" style={{ fontWeight: 600 }}>
              {row.submitted.schemaVersion}
            </span>
            <CapabilityStatusBadge status={row.submitted.status} />
          </div>
        ) : (
          <span className="text-secondary">No change submitted</span>
        ),
    },
    {
      key: 'health',
      header: 'Health',
      render: (row: SchemaRow) => <HealthStatusBadge status={(row.submitted ?? row.active).healthStatus} />,
    },
    {
      key: 'actions',
      header: 'Review',
      render: (row: SchemaRow) =>
        row.submitted ? (
          <div className="row gap-xs" style={{ justifyContent: 'flex-end' }}>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={!online}
              onClick={() => setModal({ capability: row.submitted!, decision: 'approve' })}
            >
              Approve version
            </button>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              disabled={!online}
              onClick={() => setModal({ capability: row.submitted!, decision: 'reject' })}
            >
              Reject
            </button>
          </div>
        ) : (
          <span className="text-secondary">—</span>
        ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Capability schema review"
        description="Adopt a compatible input-schema change and reject an incompatible one. The previous version stays active while the new one is under review."
      />

      {registry.status === 'loading' ? <LoadingState label="Loading schemas" /> : null}
      {registry.status === 'error' ? (
        <ErrorState error={registry.error} onRetry={() => void registry.reload()} />
      ) : null}
      {registry.status === 'success' && rows.length === 0 ? (
        <EmptyState
          title="No schemas to review"
          message="A capability with a declared input schema appears here."
        />
      ) : null}
      {registry.status === 'success' && rows.length > 0 ? (
        <DataTable
          caption="Capability schema versions"
          columns={columns}
          rows={rows}
          getRowId={(row) => row.active.capabilityId}
        />
      ) : null}

      <div className="alert alert-info" role="note" style={{ marginTop: 'var(--space-lg)' }}>
        <span aria-hidden="true">i</span>
        <span>
          A schema that requires a component outside the client catalogue is
          rejected before the version is adopted.
        </span>
      </div>

      {modal ? (
        <ReviewDialog
          capability={modal.capability}
          decision={modal.decision}
          onClose={() => setModal(null)}
          onSubmit={async (reason) => {
            await registry.run(() =>
              data.reviewCapability(modal.capability.capabilityId, {
                decision: modal.decision,
                reason: reason || null,
                schemaVersion: modal.capability.schemaVersion,
              }),
            );
            setModal(null);
          }}
        />
      ) : null}
    </>
  );
}
