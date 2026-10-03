/**
 * Fixture-backed `ConsoleData` used by demo mode and component tests. Each
 * mutating call applies the same state transition the frozen contract specifies
 * (e.g. C-016 approve → `active`, quarantine → `quarantined`) so the rendered
 * console exercises the real state machine without a backend.
 */

import { ApiError } from '../api/types';
import type {
  AuditFinding,
  AuditQuery,
  Capability,
  CreateCapabilityRequest,
  CreateProviderRequest,
  ExportRequest,
  Provider,
  ReviewRequest,
} from '../api/types';
import {
  seedAudit,
  seedCapabilities,
  seedFindings,
  seedProviders,
} from '../api/fixtures';
import type { ConsoleData } from './context';

/** Simulated latency so loading skeletons are exercised in demo mode. */
const LATENCY_MS = 250;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS));
}

let idCounter = 100;
function nextId(prefix: string): string {
  idCounter += 1;
  return `${prefix}_${idCounter}`;
}

export interface MockOptions {
  /** Force the next call to reject; lets tests exercise error/offline states. */
  failNext?: boolean;
  latency?: number;
}

export function createMockData(options: MockOptions = {}): ConsoleData & { readonly state: State } {
  const latency = options.latency ?? LATENCY_MS;
  const wait = <T>(value: T): Promise<T> =>
    new Promise((resolve) => setTimeout(() => resolve(value), latency));

  const state: State = {
    providers: structuredClone(seedProviders),
    capabilities: structuredClone(seedCapabilities),
    audit: structuredClone(seedAudit),
    findings: structuredClone(seedFindings),
    failNext: options.failNext ?? false,
  };

  function gate<T>(value: T): Promise<T> {
    if (state.failNext) {
      state.failNext = false;
      return Promise.reject(
        new ApiError(0, 'network_error', 'The console could not reach the API.'),
      );
    }
    return wait(value);
  }

  function findCapability(id: string): Capability {
    const cap = state.capabilities.find((c) => c.capabilityId === id);
    if (!cap) throw new ApiError(404, 'unknown_capability', 'Unknown capability.');
    return cap;
  }

  return {
    state,
    listProviders: () => gate(state.providers.map((p) => ({ ...p }))),
    listCapabilities: () => gate(state.capabilities.map((c) => ({ ...c }))),
    getCapability: (id) => gate({ ...findCapability(id) }),
    createProvider: (body: CreateProviderRequest) =>
      gate(addProvider(state, body)),
    createCapability: (providerId, body) => {
      if (!state.providers.some((p) => p.providerId === providerId)) {
        return Promise.reject(new ApiError(404, 'unknown_provider', 'Unknown provider.'));
      }
      return gate(addCapability(state, providerId, body));
    },
    reviewCapability: (id, body) => gate(applyReview(state, id, body)),
    async listAudit(query: AuditQuery) {
      const filtered = state.audit.filter((e) => matches(e, query));
      const limit = query.limit ?? 20;
      return gate({ entries: filtered.slice(0, limit), nextCursor: null });
    },
    listFindings: () => gate(state.findings.map((f) => ({ ...f }))),
    closeFinding: (id, body) => {
      const finding = state.findings.find((f) => f.findingsId === id);
      if (!finding) {
        return Promise.reject(new ApiError(404, 'unknown_finding', 'Unknown finding.'));
      }
      if (finding.status === 'closed') {
        return Promise.reject(new ApiError(409, 'finding_already_closed', 'Finding already closed.'));
      }
      finding.status = 'closed';
      finding.closedAt = new Date().toISOString();
      void body;
      return gate({ ...finding });
    },
    async exportAudit(body: ExportRequest) {
      void body;
      return gate({ exportId: nextId('exp'), status: 'queued' as const });
    },
  };
}

interface State {
  providers: Provider[];
  capabilities: Capability[];
  audit: ReturnType<typeof structuredClone<typeof seedAudit>>;
  findings: AuditFinding[];
  failNext: boolean;
}

function matches(entry: State['audit'][number], query: AuditQuery): boolean {
  if (query.actor && !entry.actor.includes(query.actor)) return false;
  if (query.role && !entry.role.includes(query.role)) return false;
  if (query.target && !entry.target.includes(query.target)) return false;
  if (query.action && !entry.action.includes(query.action)) return false;
  if (query.from && entry.occurredAt < query.from) return false;
  if (query.to && entry.occurredAt > query.to) return false;
  return true;
}

function addProvider(state: State, body: CreateProviderRequest): Provider {
  if (state.providers.some((p) => p.name === body.name)) {
    throw new ApiError(409, 'duplicate_provider', 'A provider with that name already exists.');
  }
  const now = new Date().toISOString();
  const provider: Provider = {
    providerId: nextId('prv'),
    name: body.name,
    type: body.type,
    contactEmail: body.contactEmail,
    status: 'pending',
    createdAt: now,
    updatedAt: now,
  };
  state.providers.unshift(provider);
  return provider;
}

function addCapability(
  state: State,
  providerId: string,
  body: CreateCapabilityRequest,
): Capability {
  if (body.serviceId && state.capabilities.some((c) => c.serviceId === body.serviceId && c.status === 'active')) {
    throw new ApiError(409, 'duplicate_capability', 'Another provider already holds this service.');
  }
  const now = new Date().toISOString();
  const capability: Capability = {
    capabilityId: nextId('cap'),
    providerId,
    name: body.name,
    serviceId: body.serviceId,
    inputSchemaRef: body.inputSchemaRef,
    amountSource: body.amountSource,
    billable: body.billable,
    priceAmount: body.priceAmount,
    priceCurrency: body.priceCurrency,
    schemaVersion: body.schemaVersion,
    status: 'pending',
    healthStatus: 'healthy',
    createdAt: now,
    updatedAt: now,
    reviews: [],
  };
  state.capabilities.unshift(capability);
  return capability;
}

function applyReview(state: State, capabilityId: string, body: ReviewRequest): Capability {
  const capability = state.capabilities.find((c) => c.capabilityId === capabilityId);
  if (!capability) throw new ApiError(404, 'unknown_capability', 'Unknown capability.');
  if (capability.status !== 'pending' && capability.status !== 'quarantined') {
    throw new ApiError(409, 'not_pending', 'Capability is not pending or quarantined.');
  }
  if (body.schemaVersion !== capability.schemaVersion) {
    throw new ApiError(409, 'schema_version_mismatch', 'Schema version does not match.');
  }
  const status: Capability['status'] =
    body.decision === 'approve'
      ? 'active'
      : body.decision === 'quarantine'
        ? 'quarantined'
        : body.decision === 'deregister'
          ? 'withdrawn'
          : 'withdrawn';
  capability.status = status;
  if (status === 'active') capability.healthStatus = 'healthy';
  capability.updatedAt = new Date().toISOString();
  capability.reviews.unshift({
    reviewId: nextId('rev'),
    capabilityId,
    decision: body.decision,
    reason: body.reason,
    schemaVersion: body.schemaVersion,
    reviewer: 'demo@sabi.ng',
    decidedAt: capability.updatedAt,
  });
  return { ...capability };
}

export { LATENCY_MS };
export { delay };
