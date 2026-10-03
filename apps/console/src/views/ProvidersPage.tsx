import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ApiError, type Capability, type Provider, type ReviewDecision } from '../api/types';
import { canReviewProviders, useAuth } from '../auth/context';
import {
  CapabilityStatusBadge,
  HealthStatusBadge,
  ProviderStatusBadge,
} from '../components/Badges';
import { DataTable, type Column, type TableSort } from '../components/DataTable';
import { ForbiddenState, PageHeader } from '../components/Page';
import { ReviewDialog } from '../components/ReviewDialog';
import { CapabilityFormDialog, ProviderFormDialog } from '../components/SubmissionDialogs';
import { EmptyState, ErrorState, LoadingState } from '../components/States';
import { useData } from '../data/context';
import { useRegistry } from '../data/useRegistry';
import { formatDate } from '../lib/format';
import { useOnline } from '../hooks/useAsync';

type Modal =
  | { kind: 'provider' }
  | { kind: 'capability'; provider: Provider }
  | { kind: 'review'; capability: Capability; decision: ReviewDecision }
  | null;

export function ProvidersPage(): JSX.Element {
  const { staff } = useAuth();
  const data = useData();
  const registry = useRegistry();
  const online = useOnline();
  const [modal, setModal] = useState<Modal>(null);
  const [selectedId, setSelectedId] = useState<string | undefined>();
  const [params, setParams] = useSearchParams();
  const query = params.get('q') ?? '';
  const [sort, setSort] = useState<TableSort>({ key: 'name', direction: 'asc' });

  const rows = useMemo(() => {
    const filtered = query
      ? registry.providers.filter((p) =>
          `${p.name} ${p.type} ${p.contactEmail}`.toLowerCase().includes(query.toLowerCase()),
        )
      : registry.providers;
    const sorted = [...filtered].sort((a, b) => {
      const dir = sort.direction === 'asc' ? 1 : -1;
      const av = String(a[sort.key as keyof Provider] ?? '');
      const bv = String(b[sort.key as keyof Provider] ?? '');
      return av.localeCompare(bv) * dir;
    });
    return sorted;
  }, [registry.providers, query, sort]);

  if (!canReviewProviders(staff?.role)) return <ForbiddenState />;

  function toggleSort(key: string) {
    setSort((s) =>
      s.key === key ? { key, direction: s.direction === 'asc' ? 'desc' : 'asc' } : { key, direction: 'asc' },
    );
  }

  const columns: Column<Provider>[] = [
    {
      key: 'name',
      header: 'Provider',
      sortValue: (p) => p.name,
      render: (p) => <span style={{ fontWeight: 600 }}>{p.name}</span>,
    },
    { key: 'type', header: 'Type', sortValue: (p) => p.type, render: (p) => p.type },
    {
      key: 'contactEmail',
      header: 'Contact',
      render: (p) => <span className="text-secondary">{p.contactEmail}</span>,
    },
    {
      key: 'status',
      header: 'Status',
      sortValue: (p) => p.status,
      render: (p) => <ProviderStatusBadge status={p.status} />,
    },
    {
      key: 'createdAt',
      header: 'Submitted',
      sortValue: (p) => p.createdAt,
      render: (p) => formatDate(p.createdAt),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (p) => (
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={(e) => {
            e.stopPropagation();
            setModal({ kind: 'capability', provider: p });
          }}
          disabled={!online}
        >
          Add capability
        </button>
      ),
    },
  ];

  const pending = registry.capabilities.filter((c) => c.status === 'pending');

  return (
    <>
      <PageHeader
        title="Provider submission and review"
        description="Capture a provider and its capability on the provider's behalf, then review the submission and record a decision."
        actions={
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setModal({ kind: 'provider' })}
            disabled={!online}
          >
            New provider
          </button>
        }
      />

      {!online ? (
        <div className="alert alert-warning" role="status" style={{ marginBottom: 'var(--space-md)' }}>
          <span aria-hidden="true">⚡</span>
          <span>Offline: submissions and review decisions are unavailable.</span>
        </div>
      ) : null}

      <div className="toolbar">
        <div className="field grow" style={{ maxWidth: 320 }}>
          <label className="field-label" htmlFor="provider-search">
            Search providers
          </label>
          <input
            id="provider-search"
            className="input"
            type="search"
            value={query}
            placeholder="Name, type, or contact"
            onChange={(e) => {
              const next = new URLSearchParams(params);
              if (e.target.value) next.set('q', e.target.value);
              else next.delete('q');
              setParams(next, { replace: true });
            }}
          />
        </div>
      </div>

      {registry.status === 'loading' ? <LoadingState label="Loading providers" /> : null}
      {registry.status === 'error' ? (
        <ErrorState error={registry.error} onRetry={() => void registry.reload()} />
      ) : null}
      {registry.status === 'success' && rows.length === 0 ? (
        <EmptyState
          title={query ? 'No providers match' : 'No provider submissions yet'}
          message={
            query
              ? 'Try a different name, type, or contact.'
              : 'Capture the first provider submission to begin review.'
          }
          action={
            query ? (
              <button type="button" className="btn btn-secondary" onClick={() => setParams({}, { replace: true })}>
                Clear search
              </button>
            ) : (
              <button type="button" className="btn btn-primary" onClick={() => setModal({ kind: 'provider' })}>
                New provider
              </button>
            )
          }
        />
      ) : null}
      {registry.status === 'success' && rows.length > 0 ? (
        <DataTable
          caption="Provider submissions"
          columns={columns}
          rows={rows}
          getRowId={(p) => p.providerId}
          sort={sort}
          onSort={toggleSort}
          selectedId={selectedId}
          onSelect={(p) => setSelectedId(p.providerId)}
        />
      ) : null}

      {registry.status === 'success' ? (
        <section style={{ marginTop: 'var(--space-2xl)' }}>
          <div className="row between gap-md wrap" style={{ marginBottom: 'var(--space-md)' }}>
            <h2 className="type-h2">Capabilities pending review</h2>
            {pending.length > 0 ? (
              <span className="badge badge-warning">
                <span aria-hidden="true">!</span>
                {pending.length} awaiting a decision
              </span>
            ) : null}
          </div>
          {pending.length === 0 ? (
            <EmptyState
              title="Nothing awaiting review"
              message="New capability submissions appear here for a decision."
            />
          ) : (
            <DataTable
              caption="Capabilities pending review"
              rows={pending}
              getRowId={(c) => c.capabilityId}
              columns={[
                { key: 'name', header: 'Capability', render: (c) => c.name },
                {
                  key: 'provider',
                  header: 'Provider',
                  render: (c) => providerName(registry.providers, c.providerId),
                },
                {
                  key: 'schemaVersion',
                  header: 'Schema',
                  render: (c) => <span className="type-mono">{c.schemaVersion}</span>,
                },
                { key: 'health', header: 'Health', render: (c) => <HealthStatusBadge status={c.healthStatus} /> },
                { key: 'status', header: 'Status', render: (c) => <CapabilityStatusBadge status={c.status} /> },
                {
                  key: 'actions',
                  header: 'Review',
                  render: (c) => (
                    <div className="row gap-xs" style={{ justifyContent: 'flex-end' }}>
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        disabled={!online}
                        onClick={() => setModal({ kind: 'review', capability: c, decision: 'approve' })}
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        disabled={!online}
                        onClick={() => setModal({ kind: 'review', capability: c, decision: 'reject' })}
                      >
                        Reject
                      </button>
                    </div>
                  ),
                },
              ]}
            />
          )}
        </section>
      ) : null}

      {modal?.kind === 'provider' ? (
        <ProviderFormDialog
          onClose={() => setModal(null)}
          onSubmit={async (body) => {
            await registry.run(() => data.createProvider(body));
            setModal(null);
          }}
        />
      ) : null}

      {modal?.kind === 'capability' ? (
        <CapabilityFormDialog
          provider={modal.provider}
          onClose={() => setModal(null)}
          onSubmit={async (body) => {
            await registry.run(() => data.createCapability(modal.provider.providerId, body));
            setModal(null);
          }}
        />
      ) : null}

      {modal?.kind === 'review' ? (
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

function providerName(providers: Provider[], providerId: string): string {
  return providers.find((p) => p.providerId === providerId)?.name ?? providerId;
}

export function reviewError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return 'The action failed.';
}
