/** Formatting helpers. Dates and amounts go through locale APIs, never string-built. */

const dateTime = new Intl.DateTimeFormat('en-NG', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'UTC',
});

const dateOnly = new Intl.DateTimeFormat('en-NG', {
  dateStyle: 'medium',
  timeZone: 'UTC',
});

export function formatDateTime(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : dateTime.format(date);
}

export function formatDate(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : dateOnly.format(date);
}

/** Amounts are integer minor units (kobo) in NGN. */
export function formatNaira(minorUnits: number | null, currency: string | null): string {
  if (minorUnits === null) return '—';
  const major = minorUnits / 100;
  return new Intl.NumberFormat('en-NG', {
    style: 'currency',
    currency: currency ?? 'NGN',
    minimumFractionDigits: 2,
  }).format(major);
}
