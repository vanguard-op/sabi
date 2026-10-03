import { createContext, useContext } from 'react';
import type {
  AuditEntry,
  AuditFinding,
  AuditPage,
  AuditQuery,
  Capability,
  CloseFindingRequest,
  CreateCapabilityRequest,
  CreateProviderRequest,
  ExportRequest,
  ExportResponse,
  ReviewRequest,
} from '../api/types';
import type { Provider } from '../api/types';

/**
 * The data surface the views depend on. The production implementation calls the
 * `/v1` gateway; the demo implementation is backed by the fixture store so the
 * console renders every state without a backend. View code depends only on this
 * interface.
 */
export interface ConsoleData {
  listProviders(): Promise<Provider[]>;
  listCapabilities(): Promise<Capability[]>;
  getCapability(capabilityId: string): Promise<Capability>;
  createProvider(body: CreateProviderRequest): Promise<Provider>;
  createCapability(providerId: string, body: CreateCapabilityRequest): Promise<Capability>;
  reviewCapability(capabilityId: string, body: ReviewRequest): Promise<Capability>;
  listAudit(query: AuditQuery): Promise<AuditPage>;
  listFindings(): Promise<AuditFinding[]>;
  closeFinding(findingsId: string, body: CloseFindingRequest): Promise<AuditFinding>;
  exportAudit(body: ExportRequest): Promise<ExportResponse>;
}

export const ConsoleDataContext = createContext<ConsoleData | null>(null);

export function useData(): ConsoleData {
  const ctx = useContext(ConsoleDataContext);
  if (!ctx) throw new Error('useData must be used within a ConsoleDataProvider');
  return ctx;
}

export type { AuditEntry };
