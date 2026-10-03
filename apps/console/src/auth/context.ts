import { createContext, useContext } from 'react';
import type { Staff, StaffRole } from '../api/types';

export interface AuthState {
  staff: Staff | null;
  status: 'checking' | 'anonymous' | 'authenticated';
  login: (staff: Staff) => void;
  logout: () => Promise<void>;
  /** Drop the local session and return to the anonymous state. */
  clear: () => void;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}

/** Roles permitted to reach each Phase 1 console surface (operations-console.md). */
export const ROLE_LABELS: Record<StaffRole, string> = {
  provider_review_analyst: 'Provider review analyst',
  administrator: 'Administrator',
  compliance_privacy_officer: 'Compliance and privacy officer',
  support_operations_agent: 'Support operations agent',
  reconciliation_officer: 'Reconciliation officer',
};

export function canReviewProviders(role: StaffRole | undefined): boolean {
  // The administrator reaches every operator surface (operations.md, "Operator
  // roles and access control": "All operator surfaces and role assignments").
  return role === 'provider_review_analyst' || role === 'administrator';
}

export function canReviewAudit(role: StaffRole | undefined): boolean {
  return role === 'compliance_privacy_officer' || role === 'administrator';
}

export function canExportAudit(role: StaffRole | undefined): boolean {
  return role === 'compliance_privacy_officer' || role === 'administrator';
}

export function canCloseFinding(role: StaffRole | undefined): boolean {
  return role === 'compliance_privacy_officer' || role === 'administrator';
}
