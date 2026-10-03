import { expect, vi } from 'vitest';
import { render, waitFor, type RenderOptions } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../auth/AuthProvider';
import { useAuth } from '../auth/context';
import { ConsoleDataContext, type ConsoleData } from '../data/context';
import type { Staff } from '../api/types';

const STAFF: Staff = {
  staffId: 'stf_1',
  email: 'a.okafor@sabi.ng',
  role: 'provider_review_analyst',
};

const AUDITOR: Staff = {
  staffId: 'stf_2',
  email: 'c.bello@sabi.ng',
  role: 'compliance_privacy_officer',
};

/**
 * Confirm the auth session for a test. The cookie is the authority, so the
 * provider asks the server; seeding storage alone would leave the operator
 * unsigned and every role-gated view would render its forbidden state.
 *
 * Only the session endpoint is stubbed. Any other request is left to the test's
 * own data layer (the mock gate), so a simulated data failure stays a data
 * failure rather than being swallowed here.
 */
function seedStaff(staff: Staff | null) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (!url.includes('/staff/auth/session')) {
        throw new Error(`unexpected network call in test: ${url}`);
      }
      if (!staff) {
        return new Response(
          JSON.stringify({ error: { code: 'unauthenticated' } }),
          { status: 401, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({ staff }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }),
  );
}

/**
 * Reports the auth status for the harness. A view only knows its role once the
 * server-confirmed session has landed, so waiting on this lets a test observe
 * the view's real states rather than the transient forbidden state it shows
 * while the session is still `checking`.
 */
function SessionProbe() {
  const { status } = useAuth();
  return <span data-testid="session-status" data-status={status} />;
}

interface Options extends Omit<RenderOptions, 'wrapper'> {
  data: ConsoleData;
  staff?: Staff | null;
  route?: string;
}

/**
 * Renders a view inside the console providers and resolves the stubbed session
 * before returning, so every test asserts against the state the authenticated
 * operator sees. This is the single place a test confirms a session.
 */
export async function renderWithProviders(
  ui: React.ReactElement,
  { data, staff = STAFF, route = '/', ...options }: Options,
) {
  seedStaff(staff);
  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <ConsoleDataContext.Provider value={data}>
        <AuthProvider>
          <MemoryRouter initialEntries={[route]}>
            <SessionProbe />
            {children}
          </MemoryRouter>
        </AuthProvider>
      </ConsoleDataContext.Provider>
    );
  }
  const result = render(ui, { wrapper: Wrapper, ...options });
  await waitFor(() =>
    expect(result.getByTestId('session-status')).not.toHaveAttribute(
      'data-status',
      'checking',
    ),
  );
  return result;
}

export { STAFF, AUDITOR };
