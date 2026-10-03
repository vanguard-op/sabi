/**
 * API client for the console. Every request targets the `/v1` gateway with
 * same-origin credentials so the HttpOnly staff session cookie travels with it.
 * A non-2xx response is normalised into `ApiError` from the error envelope.
 */

import {
  ApiError,
  type ApiErrorBody,
  type AuditPage,
  type AuditQuery,
  type Capability,
  type CloseFindingRequest,
  type CreateCapabilityRequest,
  type CreateProviderRequest,
  type ExportRequest,
  type ExportResponse,
  type LoginRequest,
  type LoginResponse,
  type Provider,
  type ReviewRequest,
} from './types';

const BASE = '/v1';

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : '';
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  let response: Response;
  try {
    const init: RequestInit = {
      method,
      credentials: 'include',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    };
    if (body !== undefined) init.body = JSON.stringify(body);
    response = await fetch(`${BASE}${path}`, init);
  } catch {
    // A network failure (offline, DNS, refused) is not an HTTP error.
    throw new ApiError(0, 'network_error', 'The console could not reach the API.');
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const json = text ? (JSON.parse(text) as unknown) : undefined;

  if (!response.ok) {
    const envelope = json as ApiErrorBody | undefined;
    throw new ApiError(
      response.status,
      envelope?.error?.code ?? 'unknown_error',
      envelope?.error?.message ?? 'The request failed.',
    );
  }

  return json as T;
}

export const api = {
  // --- Staff auth: C-039, C-040 -------------------------------------------
  login(body: LoginRequest): Promise<LoginResponse> {
    return request<LoginResponse>('POST', '/staff/auth/login', body);
  },
  logout(): Promise<void> {
    return request<void>('POST', '/staff/auth/logout');
  },

  // --- Provider registry: C-013–C-016 -------------------------------------
  createProvider(body: CreateProviderRequest): Promise<{ provider: Provider }> {
    return request<{ provider: Provider }>('POST', '/providers', body);
  },
  createCapability(
    providerId: string,
    body: CreateCapabilityRequest,
  ): Promise<{ capability: Capability }> {
    return request<{ capability: Capability }>(
      'POST',
      `/providers/${encodeURIComponent(providerId)}/capabilities`,
      body,
    );
  },
  getCapability(capabilityId: string): Promise<{ capability: Capability; healthStatus: string }> {
    return request<{ capability: Capability; healthStatus: string }>(
      'GET',
      `/capabilities/${encodeURIComponent(capabilityId)}`,
    );
  },
  reviewCapability(
    capabilityId: string,
    body: ReviewRequest,
  ): Promise<{ capability: Capability }> {
    return request<{ capability: Capability }>(
      'POST',
      `/capabilities/${encodeURIComponent(capabilityId)}/review`,
      body,
    );
  },

  // --- Audit: C-041–C-043 --------------------------------------------------
  listAudit(query: AuditQuery = {}): Promise<AuditPage> {
    return request<AuditPage>('GET', `/staff/audit${qs(query as Record<string, string | number | undefined>)}`);
  },
  closeFinding(findingsId: string, body: CloseFindingRequest): Promise<{ findingsId: string; status: string; closedAt: string }> {
    return request('POST', `/staff/audit/findings/${encodeURIComponent(findingsId)}/close`, body);
  },
  exportAudit(body: ExportRequest): Promise<ExportResponse> {
    return request<ExportResponse>('POST', '/staff/audit/export', body);
  },
};
