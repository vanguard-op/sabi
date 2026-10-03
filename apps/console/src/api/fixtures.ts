/**
 * In-memory fixtures implementing the frozen contract shapes, used by the
 * console's demo mode and by component tests. The live client is `api`; this
 * module lets the console run and be tested without a backend.
 */

import type {
  AuditEntry,
  AuditFinding,
  Capability,
  Provider,
} from './types';

const now = '2026-10-03T09:00:00Z';

export const seedProviders: Provider[] = [
  {
    providerId: 'prv_01HZQ1',
    name: 'Lagos State Water Corporation',
    type: 'biller',
    contactEmail: 'settlements@lagoswater.example.ng',
    status: 'active',
    createdAt: '2026-09-01T08:12:00Z',
    updatedAt: '2026-09-20T14:00:00Z',
  },
  {
    providerId: 'prv_01HZQ2',
    name: 'Nigerian Electricity Regulatory Collection',
    type: 'agency',
    contactEmail: 'collections@nerc.example.ng',
    status: 'pending',
    createdAt: '2026-09-28T10:30:00Z',
    updatedAt: '2026-09-28T10:30:00Z',
  },
  {
    providerId: 'prv_01HZQ3',
    name: 'SwiftPay Aggregation Ltd',
    type: 'aggregator',
    contactEmail: 'onboarding@swiftpay.example.ng',
    status: 'suspended',
    createdAt: '2026-08-11T09:00:00Z',
    updatedAt: '2026-09-15T11:45:00Z',
  },
];

export const seedCapabilities: Capability[] = [
  {
    capabilityId: 'cap_01HZA1',
    providerId: 'prv_01HZQ1',
    name: 'Water bill payment',
    serviceId: 'svc_lagos_water',
    inputSchemaRef: 'schemas/lagos-water-payment.json',
    amountSource: 'user_entered',
    billable: true,
    priceAmount: null,
    priceCurrency: 'NGN',
    schemaVersion: '2.1.0',
    status: 'active',
    healthStatus: 'healthy',
    createdAt: '2026-09-01T08:20:00Z',
    updatedAt: '2026-09-20T14:00:00Z',
    reviews: [
      {
        reviewId: 'rev_01',
        capabilityId: 'cap_01HZA1',
        decision: 'approve',
        reason: null,
        schemaVersion: '2.1.0',
        reviewer: 'a.okafor@sabi.ng',
        decidedAt: '2026-09-20T14:00:00Z',
      },
    ],
  },
  {
    capabilityId: 'cap_01HZA2',
    providerId: 'prv_01HZQ2',
    name: 'Electricity meter token',
    serviceId: 'svc_nerc_prepaid',
    inputSchemaRef: 'schemas/nerc-prepaid-token.json',
    amountSource: 'provider_query',
    billable: true,
    priceAmount: null,
    priceCurrency: 'NGN',
    schemaVersion: '1.0.0',
    status: 'pending',
    healthStatus: 'healthy',
    createdAt: '2026-09-28T10:35:00Z',
    updatedAt: '2026-09-28T10:35:00Z',
    reviews: [],
  },
  {
    capabilityId: 'cap_01HZA3',
    providerId: 'prv_01HZQ3',
    name: 'Cable TV subscription',
    serviceId: 'svc_cable_basic',
    inputSchemaRef: 'schemas/cable-subscription.json',
    amountSource: 'fixed',
    billable: true,
    priceAmount: 500000,
    priceCurrency: 'NGN',
    schemaVersion: '1.4.0',
    status: 'quarantined',
    healthStatus: 'unavailable',
    createdAt: '2026-08-11T09:10:00Z',
    updatedAt: '2026-09-15T11:45:00Z',
    reviews: [
      {
        reviewId: 'rev_02',
        capabilityId: 'cap_01HZA3',
        decision: 'quarantine',
        reason: 'Result could not be validated; possible forged receipt.',
        schemaVersion: '1.4.0',
        reviewer: 'a.okafor@sabi.ng',
        decidedAt: '2026-09-15T11:45:00Z',
      },
    ],
  },
  {
    capabilityId: 'cap_01HZA4',
    providerId: 'prv_01HZQ1',
    name: 'Water bill payment (schema 2.2.0)',
    serviceId: null,
    inputSchemaRef: 'schemas/lagos-water-payment-v220.json',
    amountSource: 'user_entered',
    billable: true,
    priceAmount: null,
    priceCurrency: 'NGN',
    schemaVersion: '2.2.0',
    status: 'pending',
    healthStatus: 'degraded',
    createdAt: '2026-10-01T12:00:00Z',
    updatedAt: '2026-10-01T12:00:00Z',
    reviews: [],
  },
];

export const seedAudit: AuditEntry[] = [
  {
    auditId: 'aud_01',
    actor: 'a.okafor@sabi.ng',
    role: 'provider_review_analyst',
    target: 'cap_01HZA1',
    action: 'capability.approve',
    reason: null,
    occurredAt: '2026-09-20T14:00:00Z',
  },
  {
    auditId: 'aud_02',
    actor: 'a.okafor@sabi.ng',
    role: 'provider_review_analyst',
    target: 'cap_01HZA3',
    action: 'capability.quarantine',
    reason: 'Result could not be validated; possible forged receipt.',
    occurredAt: '2026-09-15T11:45:00Z',
  },
  {
    auditId: 'aud_03',
    actor: 'g.eze@sabi.ng',
    role: 'administrator',
    target: 'staff_4471',
    action: 'role.grant',
    reason: 'Second approver for provider onboarding.',
    occurredAt: '2026-09-12T08:05:00Z',
  },
  {
    auditId: 'aud_04',
    actor: 'c.bello@sabi.ng',
    role: 'compliance_privacy_officer',
    target: '2026-09',
    action: 'audit.export',
    reason: 'Monthly review extract.',
    occurredAt: '2026-10-01T07:30:00Z',
  },
  {
    auditId: 'aud_05',
    actor: 'a.okafor@sabi.ng',
    role: 'provider_review_analyst',
    target: 'prv_01HZQ2',
    action: 'provider.create',
    reason: null,
    occurredAt: '2026-09-28T10:30:00Z',
  },
];

export const seedFindings: AuditFinding[] = [
  {
    findingsId: 'fnd_01',
    auditId: 'aud_02',
    summary: 'Quarantined capability has no linked health-check record.',
    status: 'open',
    openedAt: '2026-09-16T09:00:00Z',
    closedAt: null,
  },
  {
    findingsId: 'fnd_02',
    auditId: 'aud_03',
    summary: 'Role grant missing second-approver evidence.',
    status: 'open',
    openedAt: '2026-09-13T10:00:00Z',
    closedAt: null,
  },
  {
    findingsId: 'fnd_03',
    auditId: 'aud_04',
    summary: 'Export range exceeded the monthly window by one day.',
    status: 'closed',
    openedAt: '2026-09-01T06:00:00Z',
    closedAt: '2026-09-04T15:20:00Z',
  },
];

export const seedNow = now;
