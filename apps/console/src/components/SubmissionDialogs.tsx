import { useState, type FormEvent } from 'react';
import type { CreateCapabilityRequest, CreateProviderRequest, Provider, ProviderType } from '../api/types';
import { Field } from './Field';
import { Modal } from './Modal';

const TYPES: { value: ProviderType; label: string }[] = [
  { value: 'agency', label: 'Agency' },
  { value: 'biller', label: 'Biller' },
  { value: 'merchant', label: 'Merchant' },
  { value: 'aggregator', label: 'Aggregator' },
];

export function ProviderFormDialog({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (body: CreateProviderRequest) => Promise<void>;
}): JSX.Element {
  const [name, setName] = useState('');
  const [type, setType] = useState<ProviderType>('biller');
  const [contactEmail, setContactEmail] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const found: Record<string, string> = {};
    if (!name.trim()) found.name = 'Enter the provider name.';
    if (!contactEmail.trim()) found.contactEmail = 'Enter an operational contact email.';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contactEmail.trim()))
      found.contactEmail = 'Enter a valid email address.';
    setErrors(found);
    if (Object.keys(found).length) return;
    setSubmitting(true);
    try {
      await onSubmit({ name: name.trim(), type, contactEmail: contactEmail.trim() });
    } catch (err) {
      setErrors({ form: err instanceof Error ? err.message : 'The provider could not be saved.' });
      setSubmitting(false);
    }
  }

  return (
    <Modal title="New provider submission" onClose={onClose}>
      <form className="stack gap-md" onSubmit={submit} noValidate>
        {errors.form ? (
          <div className="alert alert-error" role="alert">
            <span aria-hidden="true">⚠</span>
            <span>{errors.form}</span>
          </div>
        ) : null}
        <Field label="Legal name" error={errors.name}>
          {(props) => (
            <input
              {...props}
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          )}
        </Field>
        <Field label="Provider type">
          {(props) => (
            <select
              {...props}
              className="select"
              value={type}
              onChange={(e) => setType(e.target.value as ProviderType)}
            >
              {TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Operational contact" error={errors.contactEmail}>
          {(props) => (
            <input
              {...props}
              className="input"
              type="email"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
            />
          )}
        </Field>
        <div className="row gap-sm between">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Submitting…' : 'Create provider'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function CapabilityFormDialog({
  provider,
  onClose,
  onSubmit,
}: {
  provider: Provider;
  onClose: () => void;
  onSubmit: (body: CreateCapabilityRequest) => Promise<void>;
}): JSX.Element {
  const [name, setName] = useState('');
  const [serviceId, setServiceId] = useState('');
  const [inputSchemaRef, setInputSchemaRef] = useState('');
  const [amountSource, setAmountSource] = useState<CreateCapabilityRequest['amountSource']>('user_entered');
  const [billable, setBillable] = useState(true);
  const [priceAmount, setPriceAmount] = useState('');
  const [schemaVersion, setSchemaVersion] = useState('1.0.0');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const found: Record<string, string> = {};
    if (!name.trim()) found.name = 'Enter the capability name.';
    if (!inputSchemaRef.trim()) found.inputSchemaRef = 'Reference the input schema.';
    if (!schemaVersion.trim()) found.schemaVersion = 'Declare the schema version.';
    else if (!/^\d+\.\d+\.\d+$/.test(schemaVersion.trim()))
      found.schemaVersion = 'Use a semantic version, for example 2.1.0.';
    if (amountSource === 'fixed') {
      const n = Number(priceAmount);
      if (!priceAmount || !Number.isInteger(n) || n <= 0)
        found.priceAmount = 'A fixed amount is stated in kobo, whole naira × 100.';
    }
    setErrors(found);
    if (Object.keys(found).length) return;
    setSubmitting(true);
    try {
      await onSubmit({
        name: name.trim(),
        serviceId: serviceId.trim() || null,
        inputSchemaRef: inputSchemaRef.trim(),
        amountSource,
        billable,
        priceAmount: amountSource === 'fixed' ? Number(priceAmount) : null,
        priceCurrency: 'NGN',
        schemaVersion: schemaVersion.trim(),
      });
    } catch (err) {
      setErrors({ form: err instanceof Error ? err.message : 'The capability could not be saved.' });
      setSubmitting(false);
    }
  }

  return (
    <Modal title={`New capability for ${provider.name}`} onClose={onClose}>
      <form className="stack gap-md" onSubmit={submit} noValidate>
        {errors.form ? (
          <div className="alert alert-error" role="alert">
            <span aria-hidden="true">⚠</span>
            <span>{errors.form}</span>
          </div>
        ) : null}
        <Field label="Capability name" error={errors.name}>
          {(props) => (
            <input {...props} className="input" value={name} onChange={(e) => setName(e.target.value)} />
          )}
        </Field>
        <Field label="Claimed service id" optional hint="Leave blank to submit a new version of an existing capability.">
          {(props) => (
            <input
              {...props}
              className="input type-mono"
              value={serviceId}
              onChange={(e) => setServiceId(e.target.value)}
            />
          )}
        </Field>
        <Field label="Input schema reference" error={errors.inputSchemaRef}>
          {(props) => (
            <input
              {...props}
              className="input type-mono"
              value={inputSchemaRef}
              onChange={(e) => setInputSchemaRef(e.target.value)}
            />
          )}
        </Field>
        <Field label="Amount source">
          {(props) => (
            <select
              {...props}
              className="select"
              value={amountSource}
              onChange={(e) => setAmountSource(e.target.value as CreateCapabilityRequest['amountSource'])}
            >
              <option value="fixed">Fixed</option>
              <option value="user_entered">User entered</option>
              <option value="provider_query">Provider query</option>
            </select>
          )}
        </Field>
        {amountSource === 'fixed' ? (
          <Field label="Fixed price (kobo)" error={errors.priceAmount}>
            {(props) => (
              <input
                {...props}
                className="input type-mono"
                inputMode="numeric"
                value={priceAmount}
                onChange={(e) => setPriceAmount(e.target.value.replace(/\D/g, ''))}
              />
            )}
          </Field>
        ) : null}
        <Field label="Schema version" error={errors.schemaVersion}>
          {(props) => (
            <input
              {...props}
              className="input type-mono"
              value={schemaVersion}
              onChange={(e) => setSchemaVersion(e.target.value)}
            />
          )}
        </Field>
        <label className="checkbox-field">
          <input type="checkbox" checked={billable} onChange={(e) => setBillable(e.target.checked)} />
          <span>Billable to the user</span>
        </label>
        <div className="row gap-sm between">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Submitting…' : 'Create capability'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
