import type { CapabilityStatus, HealthStatus, ProviderStatus } from '../api/types';

type Tone = 'neutral' | 'success' | 'warning' | 'error' | 'info';

const PROVIDER_TONES: Record<ProviderStatus, Tone> = {
  pending: 'warning',
  active: 'success',
  suspended: 'warning',
  deregistered: 'neutral',
};

const CAPABILITY_TONES: Record<CapabilityStatus, Tone> = {
  pending: 'warning',
  active: 'success',
  withdrawn: 'neutral',
  quarantined: 'error',
};

const HEALTH_TONES: Record<HealthStatus, Tone> = {
  healthy: 'success',
  degraded: 'warning',
  unavailable: 'error',
};

const PROVIDER_LABELS: Record<ProviderStatus, string> = {
  pending: 'Pending review',
  active: 'Active',
  suspended: 'Suspended',
  deregistered: 'Deregistered',
};

const CAPABILITY_LABELS: Record<CapabilityStatus, string> = {
  pending: 'Pending review',
  active: 'Active',
  withdrawn: 'Withdrawn',
  quarantined: 'Quarantined',
};

const HEALTH_LABELS: Record<HealthStatus, string> = {
  healthy: 'Healthy',
  degraded: 'Degraded',
  unavailable: 'Unavailable',
};

const GLYPHS: Record<Tone, string> = {
  neutral: '•',
  success: '✓',
  warning: '!',
  error: '×',
  info: 'i',
};

function Badge({ tone, label }: { tone: Tone; label: string }): JSX.Element {
  return (
    <span className={`badge badge-${tone}`}>
      <span aria-hidden="true">{GLYPHS[tone]}</span>
      {label}
    </span>
  );
}

export function ProviderStatusBadge({ status }: { status: ProviderStatus }): JSX.Element {
  return <Badge tone={PROVIDER_TONES[status]} label={PROVIDER_LABELS[status]} />;
}

export function CapabilityStatusBadge({ status }: { status: CapabilityStatus }): JSX.Element {
  return <Badge tone={CAPABILITY_TONES[status]} label={CAPABILITY_LABELS[status]} />;
}

export function HealthStatusBadge({ status }: { status: HealthStatus }): JSX.Element {
  return <Badge tone={HEALTH_TONES[status]} label={HEALTH_LABELS[status]} />;
}
