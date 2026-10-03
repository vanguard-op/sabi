/**
 * Wire types for the Operations Console, conforming to the frozen contracts in
 * `CONTRACTS.md`: provider registry C-013–C-016 and staff-auth / audit
 * C-039–C-043. Field names are camelCase and timestamps are RFC 3339 UTC.
 */

export type ProviderType = 'agency' | 'biller' | 'merchant' | 'aggregator';
export type ProviderStatus = 'pending' | 'active' | 'suspended' | 'deregistered';

export type CapabilityStatus =
  | 'pending'
  | 'active'
  | 'withdrawn'
  | 'quarantined';

export type HealthStatus = 'healthy' | 'degraded' | 'unavailable';

export type AmountSource = 'fixed' | 'user_entered' | 'provider_query';

export type ReviewDecision = 'approve' | 'reject' | 'quarantine' | 'deregister';

export interface Provider {
  providerId: string;
  name: string;
  type: ProviderType;
  contactEmail: string;
  status: ProviderStatus;
  createdAt: string;
  updatedAt: string;
}

export interface CapabilityReview {
  reviewId: string;
  capabilityId: string;
  decision: ReviewDecision;
  reason: string | null;
  schemaVersion: string;
  reviewer: string;
  decidedAt: string;
}

export interface Capability {
  capabilityId: string;
  providerId: string;
  name: string;
  serviceId: string | null;
  inputSchemaRef: string;
  amountSource: AmountSource;
  billable: boolean;
  priceAmount: number | null;
  priceCurrency: string | null;
  schemaVersion: string;
  status: CapabilityStatus;
  healthStatus: HealthStatus;
  createdAt: string;
  updatedAt: string;
  reviews: CapabilityReview[];
}

export interface CreateProviderRequest {
  name: string;
  type: ProviderType;
  contactEmail: string;
}

export interface CreateCapabilityRequest {
  name: string;
  serviceId: string | null;
  inputSchemaRef: string;
  amountSource: AmountSource;
  billable: boolean;
  priceAmount: number | null;
  priceCurrency: string | null;
  schemaVersion: string;
}

export interface ReviewRequest {
  decision: ReviewDecision;
  reason: string | null;
  schemaVersion: string;
}

/** C-016 returns the updated capability; the console treats it as a Capability. */
export interface CapabilityRecord extends Capability {}

export type StaffRole =
  | 'provider_review_analyst'
  | 'administrator'
  | 'compliance_privacy_officer'
  | 'support_operations_agent'
  | 'reconciliation_officer';

export interface Staff {
  staffId: string;
  email: string;
  role: StaffRole;
}

export interface LoginRequest {
  email: string;
  password: string;
  totp: string;
}

export interface LoginResponse {
  staff: Staff;
  mustEnrolMfa: boolean;
}

export interface AuditEntry {
  auditId: string;
  actor: string;
  role: string;
  target: string;
  action: string;
  reason: string | null;
  occurredAt: string;
}

export interface AuditQuery {
  actor?: string;
  role?: string;
  target?: string;
  action?: string;
  from?: string;
  to?: string;
  cursor?: string;
  limit?: number;
}

export interface AuditPage {
  entries: AuditEntry[];
  nextCursor: string | null;
}

/** A flagged review finding surfaced in the audit view. */
export interface AuditFinding {
  findingsId: string;
  auditId: string;
  summary: string;
  status: 'open' | 'closed';
  openedAt: string;
  closedAt: string | null;
}

export interface CloseFindingRequest {
  resolution: string;
}

export interface ExportRequest {
  from: string;
  to: string;
  format: 'csv' | 'json';
}

export interface ExportResponse {
  exportId: string;
  status: 'queued';
}

/** Error envelope from DELIVERY.md conventions. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}
