import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuditPage } from '../views/AuditPage';
import { createMockData } from '../data/mockData';
import { AUDITOR, renderWithProviders } from '../test/render';

/** The privileged-action table, scoped so an actor name is not matched in a finding. */
function auditTable(): HTMLElement {
  return screen.getByRole('table', { name: /privileged actions/i });
}

/** Waits for the audit read to settle on a rendered timeline. */
async function auditReady(): Promise<HTMLElement> {
  return screen.findByRole('table', { name: /privileged actions/i });
}

describe('AuditPage', () => {
  it('renders the audit timeline with a high-risk flag', async () => {
    const data = createMockData();
    await renderWithProviders(<AuditPage />, { data, staff: AUDITOR });
    const table = await auditReady();
    expect(within(table).getAllByText(/a.okafor@sabi.ng/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/high risk/i).length).toBeGreaterThan(0);
  });

  it('filters the log by actor', async () => {
    const data = createMockData();
    await renderWithProviders(<AuditPage />, { data, staff: AUDITOR });
    await auditReady();

    await userEvent.type(screen.getByLabelText(/^actor$/i), 'g.eze');
    await userEvent.click(screen.getByRole('button', { name: /apply/i }));

    await waitFor(() =>
      expect(screen.queryByText(/capability approve/i)).not.toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(within(auditTable()).getByText(/role grant/i)).toBeInTheDocument(),
    );
  });

  it('shows an empty state when no entries match', async () => {
    const data = createMockData();
    await renderWithProviders(<AuditPage />, { data, staff: AUDITOR });
    await auditReady();

    await userEvent.type(screen.getByLabelText(/^actor$/i), 'nobody');
    await userEvent.click(screen.getByRole('button', { name: /apply/i }));

    expect(await screen.findByText(/no audit entries match/i)).toBeInTheDocument();
  });

  it('lists open findings and closes one', async () => {
    const data = createMockData();
    await renderWithProviders(<AuditPage />, { data, staff: AUDITOR });
    expect(
      await screen.findByText(/Quarantined capability has no linked health-check record/i),
    ).toBeInTheDocument();

    // Two findings are open, so two rows offer the action.
    expect(screen.getAllByRole('button', { name: /close finding/i })).toHaveLength(2);

    await userEvent.click(screen.getAllByRole('button', { name: /close finding/i })[0]!);
    await userEvent.type(screen.getByLabelText(/resolution/i), 'Linked the health-check record.');
    const dialog = await screen.findByRole('dialog', { name: /close finding/i });
    await userEvent.click(within(dialog).getByRole('button', { name: /^close finding$/i }));

    // The closed finding leaves the open set once the list reloads.
    await waitFor(() =>
      expect(screen.getAllByRole('button', { name: /close finding/i })).toHaveLength(1),
    );
  });

  it('validates the export range', async () => {
    const data = createMockData();
    await renderWithProviders(<AuditPage />, { data, staff: AUDITOR });
    await auditReady();

    await userEvent.click(screen.getByRole('button', { name: /export extract/i }));
    await userEvent.click(screen.getByRole('button', { name: /queue export/i }));
    expect(await screen.findByText(/choose a start and end date/i)).toBeInTheDocument();
  });

  it('queues an export and reports it', async () => {
    const data = createMockData();
    await renderWithProviders(<AuditPage />, { data, staff: AUDITOR });
    await auditReady();

    await userEvent.click(screen.getByRole('button', { name: /export extract/i }));
    const dialog = await screen.findByRole('dialog', { name: /export audit extract/i });
    const from = within(dialog).getByLabelText(/^from$/i) as HTMLInputElement;
    const to = within(dialog).getByLabelText(/^to$/i) as HTMLInputElement;
    await userEvent.type(from, '2026-09-01');
    await userEvent.type(to, '2026-09-30');
    await userEvent.click(screen.getByRole('button', { name: /queue export/i }));

    expect(await screen.findByText(/export exp_\d+ queued/i)).toBeInTheDocument();
  });

  it('does not offer export to an administrator', async () => {
    const data = createMockData();
    await renderWithProviders(<AuditPage />, {
      data,
      staff: { staffId: 's', email: 'g.eze@sabi.ng', role: 'administrator' },
    });
    await auditReady();
    expect(screen.queryByRole('button', { name: /export extract/i })).not.toBeInTheDocument();
  });

  it('blocks a role that may not read the audit log', async () => {
    const data = createMockData();
    await renderWithProviders(<AuditPage />, {
      data,
      staff: { staffId: 's', email: 'a@sabi.ng', role: 'provider_review_analyst' },
    });
    expect(await screen.findByText(/not available for your role/i)).toBeInTheDocument();
  });

  it('shows an error state when the audit read fails', async () => {
    const data = createMockData();
    data.state.failNext = true;
    await renderWithProviders(<AuditPage />, { data, staff: AUDITOR });
    expect(await screen.findByText(/could not reach the api/i)).toBeInTheDocument();
  });
});
