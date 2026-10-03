import { vi } from 'vitest';
import { render, type RenderOptions } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../auth/AuthProvider';
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

interface Options extends Omit<RenderOptions, 'wrapper'> {
  data: ConsoleData;
  staff?: Staff | null;
  route?: string;
}

export function renderWithProviders(
  ui: React.ReactElement,
  { data, staff = STAFF, route = '/', ...options }: Options,
) {
  seedStaff(staff);
  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <ConsoleDataContext.Provider value={data}>
        <AuthProvider>
          <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
        </AuthProvider>
      </ConsoleDataContext.Provider>
    );
  }
  return render(ui, { wrapper: Wrapper, ...options });
}

export { STAFF, AUDITOR };
