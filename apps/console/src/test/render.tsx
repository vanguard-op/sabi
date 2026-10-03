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

/** Seeds the auth session mirror without going through the login form. */
function seedStaff(staff: Staff | null) {
  if (staff) sessionStorage.setItem('sabi.console.staff', JSON.stringify(staff));
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
