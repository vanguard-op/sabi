import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProvidersPage } from '../views/ProvidersPage';
import { createMockData } from '../data/mockData';
import { renderWithProviders } from '../test/render';
import type { ConsoleData } from '../data/context';
import { ApiError } from '../api/types';

/** The provider registry table, scoped so its rows are not confused with the pending-capability table. */
function providerTable(): HTMLElement {
  return screen.getByRole('table', { name: /provider submissions/i });
}

describe('ProvidersPage', () => {
  it('shows a loading state before the registry resolves', async () => {
    const data = createMockData({ latency: 500 });
    await renderWithProviders(<ProvidersPage />, { data });
    expect(screen.getByText(/loading providers/i)).toBeInTheDocument();
    await waitFor(
      () => expect(within(providerTable()).getByText(/Lagos State Water/i)).toBeInTheDocument(),
      { timeout: 2000 },
    );
  });

  it('shows an empty state when there are no provider submissions', async () => {
    const data = createMockData();
    data.state.providers = [];
    await renderWithProviders(<ProvidersPage />, { data });
    expect(await screen.findByText(/no provider submissions yet/i)).toBeInTheDocument();
  });

  it('shows an error state with a retry when the load fails', async () => {
    const data = createMockData();
    data.state.failNext = true;
    await renderWithProviders(<ProvidersPage />, { data });
    expect(await screen.findByText(/could not reach the api/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('validates the provider form before submitting', async () => {
    const data = createMockData();
    const createProvider = vi.spyOn(data, 'createProvider');
    await renderWithProviders(<ProvidersPage />, { data });
    await screen.findByRole('heading', { name: /capabilities pending review/i });

    await userEvent.click(screen.getByRole('button', { name: /new provider/i }));
    await userEvent.click(screen.getByRole('button', { name: /create provider/i }));

    expect(await screen.findByText(/enter the provider name/i)).toBeInTheDocument();
    expect(screen.getByText(/enter an operational contact email/i)).toBeInTheDocument();
    expect(createProvider).not.toHaveBeenCalled();
  });

  it('creates a provider and surfaces it in the table', async () => {
    const data = createMockData();
    await renderWithProviders(<ProvidersPage />, { data });
    await screen.findByRole('heading', { name: /capabilities pending review/i });

    await userEvent.click(screen.getByRole('button', { name: /new provider/i }));
    await userEvent.type(screen.getByLabelText(/legal name/i), 'Kano Metropolis Water Board');
    await userEvent.type(screen.getByLabelText(/operational contact/i), 'ops@kano.example.ng');
    await userEvent.click(screen.getByRole('button', { name: /create provider/i }));

    await waitFor(() =>
      expect(
        within(providerTable()).getByText(/Kano Metropolis Water Board/i),
      ).toBeInTheDocument(),
    );
  });

  it('shows a submitting state and records an approval decision', async () => {
    const data = createMockData();
    await renderWithProviders(<ProvidersPage />, { data });
    await screen.findByRole('heading', { name: /capabilities pending review/i });
    await screen.findByText(/Electricity meter token/i);

    const pending = screen.getByRole('table', { name: /capabilities pending review/i });
    await userEvent.click(within(pending).getAllByRole('button', { name: /^approve$/i })[0]!);

    const dialog = await screen.findByRole('dialog', { name: /approve capability/i });
    await userEvent.click(within(dialog).getByRole('button', { name: /^approve$/i }));

    await waitFor(() =>
      expect(screen.queryByText(/Electricity meter token/i)).not.toBeInTheDocument(),
    );
  });

  it('requires a reason before recording a rejection', async () => {
    const data = createMockData();
    await renderWithProviders(<ProvidersPage />, { data });
    await screen.findByRole('heading', { name: /capabilities pending review/i });

    const pending = screen.getByRole('table', { name: /capabilities pending review/i });
    await userEvent.click(within(pending).getAllByRole('button', { name: /^reject$/i })[0]!);

    const dialog = await screen.findByRole('dialog', { name: /reject capability/i });
    await userEvent.click(within(dialog).getByRole('button', { name: /^reject$/i }));

    expect(await screen.findByText(/give a reason for this decision/i)).toBeInTheDocument();
  });

  it('blocks a reviewer role that is not permitted', async () => {
    const data = createMockData();
    await renderWithProviders(<ProvidersPage />, {
      data,
      staff: { staffId: 's', email: 'x@sabi.ng', role: 'compliance_privacy_officer' },
    });
    expect(await screen.findByText(/not available for your role/i)).toBeInTheDocument();
  });
});

describe('ProvidersPage offline', () => {
  it('disables the submission actions when offline', async () => {
    const data = createMockData();
    const original = window.navigator.onLine;
    Object.defineProperty(window.navigator, 'onLine', { writable: true, value: false });
    window.dispatchEvent(new Event('offline'));
    try {
      await renderWithProviders(<ProvidersPage />, { data });
      await waitFor(() =>
        expect(within(providerTable()).getByText(/Lagos State Water/i)).toBeInTheDocument(),
      );
      expect(screen.getByRole('button', { name: /new provider/i })).toBeDisabled();
      expect(screen.getByText(/offline: submissions and review decisions/i)).toBeInTheDocument();
    } finally {
      Object.defineProperty(window.navigator, 'onLine', { writable: true, value: original });
      window.dispatchEvent(new Event('online'));
    }
  });
});

describe('ProvidersPage duplicate handling', () => {
  it('surfaces a conflict from the API in the form', async () => {
    const data: ConsoleData = {
      ...createMockData(),
      createProvider: () =>
        Promise.reject(new ApiError(409, 'duplicate_provider', 'A provider with that name already exists.')),
    };
    await renderWithProviders(<ProvidersPage />, { data });
    await screen.findByRole('heading', { name: /capabilities pending review/i });

    await userEvent.click(screen.getByRole('button', { name: /new provider/i }));
    await userEvent.type(screen.getByLabelText(/legal name/i), 'Dup');
    await userEvent.type(screen.getByLabelText(/operational contact/i), 'a@b.ng');
    await userEvent.click(screen.getByRole('button', { name: /create provider/i }));

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
  });
});
