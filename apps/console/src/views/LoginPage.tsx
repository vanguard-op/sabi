import { useState, type FormEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { ApiError } from '../api/types';
import { useAuth } from '../auth/context';
import { useOnline } from '../hooks/useAsync';
import { Field } from '../components/Field';
import { OfflineState } from '../components/States';

interface Errors {
  email?: string;
  password?: string;
  totp?: string;
  form?: string;
}

function validate(email: string, password: string, totp: string): Errors {
  const errors: Errors = {};
  if (!email.trim()) errors.email = 'Enter your staff email.';
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
    errors.email = 'Enter a valid email address.';
  if (!password) errors.password = 'Enter your password.';
  if (!totp.trim()) errors.totp = 'Enter the six-digit code from your authenticator.';
  else if (!/^\d{6}$/.test(totp.trim())) errors.totp = 'The code is six digits.';
  return errors;
}

function messageFor(error: ApiError): string {
  switch (error.status) {
    case 401:
      return 'Email, password, or code did not match. Try again.';
    case 403:
      return 'This account does not hold an operator role. Contact an administrator.';
    case 423:
      return 'This account is locked after repeated failures. Contact an administrator.';
    case 429:
      return 'Too many attempts. Wait a moment before trying again.';
    default:
      return error.message;
  }
}

export function LoginPage(): JSX.Element {
  const { login } = useAuth();
  const online = useOnline();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? '/providers';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [totp, setTotp] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);

  if (!online) {
    return (
      <div className="login-page">
        <div className="login-card">
          <OfflineState />
        </div>
      </div>
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const found = validate(email, password, totp);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setSubmitting(true);
    try {
      const result = await api.login({ email: email.trim(), password, totp: totp.trim() });
      login(result.staff);
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors({ form: messageFor(err) });
      } else {
        setErrors({ form: 'Something went wrong. Try again.' });
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="stack gap-xs" style={{ marginBottom: 'var(--space-lg)' }}>
          <h1 className="type-h1">Operations Console</h1>
          <p className="type-body text-secondary">
            Staff sign-in with your email, password, and authenticator code.
          </p>
        </div>

        {errors.form ? (
          <div className="alert alert-error" role="alert" style={{ marginBottom: 'var(--space-md)' }}>
            <span aria-hidden="true">⚠</span>
            <span>{errors.form}</span>
          </div>
        ) : null}

        <form className="stack gap-md" onSubmit={onSubmit} noValidate>
          <Field label="Staff email" error={errors.email}>
            {(props) => (
              <input
                {...props}
                className="input"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
          </Field>
          <Field label="Password" error={errors.password}>
            {(props) => (
              <input
                {...props}
                className="input"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            )}
          </Field>
          <Field
            label="Authenticator code"
            error={errors.totp}
            hint="The six-digit code from your authenticator app."
          >
            {(props) => (
              <input
                {...props}
                className="input type-mono"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={totp}
                onChange={(e) => setTotp(e.target.value.replace(/\D/g, ''))}
              />
            )}
          </Field>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  );
}
