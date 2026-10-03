import { useMemo, useState } from 'react';
import type { Capability, HealthStatus, ReviewDecision } from '../api/types';
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

const HEALTH_FILTERS: { value: HealthStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All health states' },
  { value: 'healthy', label: 'Healthy' },
  { value: 'degraded', label: 'Degraded' },
  { value: 'unavailable', label: 'Unavailable' },
];

export function HealthPage(): JSX.Element {
  const { staff } = useAuth();
  const data = useData();
  const registry = useRegistry();
  const online = useOnline();
  const [filter, setFilter] = useState<HealthStatus | 'all'>('all');
  const [modal, setModal] = useState<{ capability: Capability; decision: ReviewDecision } | null>(null);

  const rows = useMemo(
    () =>
      registry.capabilities.filter((c) =>
        filter === 'all' ? true : c.healthStatus === filter,
      ),
    [registry.capabilities, filter],
  );

  const counts = useMemo(() => {
    const base: Record<HealthStatus | 'quarantined', number> = {
      healthy: 0,
      degraded: 0,
      unavailable: 0,
      quarantined: 0,
    };
    for (const c of registry.capabilities) {
      if (c.status === 'quarantined') base.quarantined += 1;
      else base[c.healthStatus] += 1;
    }
    return base;
  }, [registry.capabilities]);

  if (!canReviewProviders(staff?.role)) return <ForbiddenState />;

  const columns = [
    {
      key: 'capability',
      header: 'Capability',
      render: (c: Capability) => (
        <div className="stack">
          <span style={{ fontWeight: 600 }}>{c.name}</span>
          <span className="type-caption text-secondary type-mono">{c.capabilityId}</span>
        </div>
      ),
    },
    {
      key: 'health',
      header: 'Health',
      render: (c: Capability) => <HealthStatusBadge status={c.healthStatus} />,
    },
    {
      key: 'status',
      header: 'Status',
      render: (c: Capability) => <CapabilityStatusBadge status={c.status} />,
    },
    {
      key: 'schemaVersion',
      header: 'Schema',
      render: (c: Capability) => <span className="type-mono">{c.schemaVersion}</span>,
    },
    {
      key: 'updatedAt',
      header: 'Last result',
      render: (c: Capability) => formatDateTime(c.updatedAt),
    },
    {
      key: 'actions',
      header: 'Action',
      render: (c: Capability) => {
        // Restore is offered when a capability is quarantined; otherwise an
        // unhealthy capability can be quarantined or moved to deregistration.
        if (c.status === 'quarantined' || c.status === 'active') {
          return (
            <div className="row gap-xs" style={{ justifyContent: 'flex-end' }}>
              {c.status === 'quarantined' ? (
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={!online}
                  onClick={() => setModal({ capability: c, decision: 'approve' })}
                >
                  Restore
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-outline btn-sm"
                  disabled={!online}
                  onClick={() => setModal({ capability: c, decision: 'quarantine' })}
                >
                  Quarantine
                </button>
              )}
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={!online}
                onClick={() => setModal({ capability: c, decision: 'deregister' })}
              >
                Deregister
              </button>
            </div>
          );
        }
        return <span className="text-secondary">—</span>;
      },
    },
  ];

  return (
    <>
      <PageHeader
        title="Capability health and quarantine"
        description="See the latest health result for each capability, withdraw an unhealthy or forged capability from discovery, and restore it after a fix."
      />

      <div className="row gap-md wrap" style={{ marginBottom: 'var(--space-md)' }}>
        <span className="badge badge-success">
          <span aria-hidden="true">✓</span>
          {counts.healthy} healthy
        </span>
        <span className="badge badge-warning">
          <span aria-hidden="true">!</span>
          {counts.degraded} degraded
        </span>
        <span className="badge badge-error">
          <span aria-hidden="true">×</span>
          {counts.unavailable} unavailable
        </span>
        <span className="badge badge-error">
          <span aria-hidden="true">×</span>
          {counts.quarantined} quarantined
        </span>
      </div>

      <div className="toolbar">
        <div className="field">
          <label className="field-label" htmlFor="health-filter">
            Filter by health
          </label>
          <select
            id="health-filter"
            className="select"
            value={filter}
            onChange={(e) => setFilter(e.target.value as HealthStatus | 'all')}
          >
            {HEALTH_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {registry.status === 'loading' ? <LoadingState label="Loading health results" /> : null}
      {registry.status === 'error' ? (
        <ErrorState error={registry.error} onRetry={() => void registry.reload()} />
      ) : null}
      {registry.status === 'success' && rows.length === 0 ? (
        <EmptyState
          title="No capabilities in this state"
          message="Change the filter to see other health results."
        />
      ) : null}
      {registry.status === 'success' && rows.length > 0 ? (
        <DataTable
          caption="Capability health results"
          columns={columns}
          rows={rows}
          getRowId={(c) => c.capabilityId}
        />
      ) : null}

      <div className="alert alert-info" role="note" style={{ marginTop: 'var(--space-lg)' }}>
        <span aria-hidden="true">i</span>
        <span>
          A manual health re-check is not available in Phase 1; the scheduled
          check updates this view.
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
