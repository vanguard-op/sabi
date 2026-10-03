import { useState, type FormEvent } from 'react';
import type { Capability, ReviewDecision } from '../api/types';
import { Field } from './Field';
import { Modal } from './Modal';

const DECISION_LABELS: Record<ReviewDecision, string> = {
  approve: 'Approve',
  reject: 'Reject',
  quarantine: 'Quarantine',
  deregister: 'Deregister',
};

const DECISION_HINTS: Record<ReviewDecision, string> = {
  approve: 'Approves the capability and makes it discoverable.',
  reject: 'Returns the submission to the provider for correction.',
  quarantine: 'Removes the capability from discovery pending review.',
  deregister: 'Withdraws the capability from the offering.',
};

/**
 * Records a review decision against a capability (C-016). A reason is required
 * for every decision except approve; a quarantine, reject, or deregister
 * without one is meaningless in the audit trail.
 */
export function ReviewDialog({
  capability,
  decision,
  onClose,
  onSubmit,
}: {
  capability: Capability;
  decision: ReviewDecision;
  onClose: () => void;
  onSubmit: (reason: string) => Promise<void>;
}): JSX.Element {
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const destructive = decision === 'quarantine' || decision === 'deregister' || decision === 'reject';

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (decision !== 'approve' && !reason.trim()) {
      setError('Give a reason for this decision.');
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit(reason.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The decision could not be saved.');
      setSubmitting(false);
    }
  }

  return (
    <Modal title={`${DECISION_LABELS[decision]} capability`} onClose={onClose}>
      <form className="stack gap-md" onSubmit={submit} noValidate>
        <dl className="detail-list">
          <dt>Capability</dt>
          <dd>{capability.name}</dd>
          <dt>Schema version</dt>
          <dd className="type-mono">{capability.schemaVersion}</dd>
        </dl>
        <p className={`alert alert-${destructive ? 'warning' : 'info'}`}>
          <span aria-hidden="true">{destructive ? '!' : 'i'}</span>
          <span>{DECISION_HINTS[decision]}</span>
        </p>
        <Field
          label="Reason"
          optional={decision === 'approve'}
          error={error}
          hint="Recorded in the audit log against your operator identity."
        >
          {(props) => (
            <textarea
              {...props}
              className="textarea"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          )}
        </Field>
        <div className="row gap-sm between">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button
            type="submit"
            className={`btn ${destructive ? 'btn-destructive' : 'btn-primary'}`}
            disabled={submitting}
          >
            {submitting ? 'Saving…' : DECISION_LABELS[decision]}
          </button>
        </div>
      </form>
    </Modal>
  );
}
