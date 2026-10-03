/**
 * Production `ConsoleData` implementation over the `/v1` gateway. C-013/C-014
 * return a single created entity; the list views derive their tables from the
 * fixture-free responses the API exposes. Since the frozen contracts expose
 * create/read/review but no provider-list endpoint, the console keeps a local
 * working set seeded from what it has created and reviewed in the session, and
 * the review detail refetches the capability by id (C-015).
 */

import { api } from '../api/client';
import type {
  AuditFinding,
  AuditPage,
  AuditQuery,
  Capability,
  CloseFindingRequest,
  CreateCapabilityRequest,
  CreateProviderRequest,
  ExportRequest,
  ExportResponse,
  Provider,
  ReviewRequest,
} from '../api/types';
import type { ConsoleData } from './context';

export function createLiveData(): ConsoleData {
  // Session working sets. The registry has no list endpoint in Phase 1, so the
  // console accumulates what it creates and what it has fetched by id.
  const providers = new Map<string, Provider>();
  const capabilities = new Map<string, Capability>();

  function rememberCapability(cap: Capability): Capability {
    capabilities.set(cap.capabilityId, cap);
    return cap;
  }

  return {
    async listProviders() {
      return [...providers.values()];
    },
    async listCapabilities() {
      return [...capabilities.values()];
    },
    async getCapability(capabilityId) {
      const { capability } = await api.getCapability(capabilityId);
      return rememberCapability(capability);
    },
    async createProvider(body: CreateProviderRequest) {
      const { provider } = await api.createProvider(body);
      providers.set(provider.providerId, provider);
      return provider;
    },
    async createCapability(providerId, body: CreateCapabilityRequest) {
      const { capability } = await api.createCapability(providerId, body);
      return rememberCapability(capability);
    },
    async reviewCapability(capabilityId, body: ReviewRequest) {
      const { capability } = await api.reviewCapability(capabilityId, body);
      return rememberCapability(capability);
    },
    async listAudit(query: AuditQuery): Promise<AuditPage> {
      return api.listAudit(query);
    },
    async listFindings(): Promise<AuditFinding[]> {
      // Findings have no read endpoint in Phase 1; the audit view surfaces them
      // from the close endpoint's contract shape. Until one exists the live
      // console reports no open findings.
      return [];
    },
    async closeFinding(findingsId: string, body: CloseFindingRequest) {
      await api.closeFinding(findingsId, body);
      return {
        findingsId,
        auditId: '',
        summary: '',
        status: 'closed',
        openedAt: '',
        closedAt: new Date().toISOString(),
      };
    },
    async exportAudit(body: ExportRequest): Promise<ExportResponse> {
      return api.exportAudit(body);
    },
  };
}
