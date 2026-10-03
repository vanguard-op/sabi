import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProvidersPage } from '../views/ProvidersPage';
import { createMockData } from '../data/mockData';
import { renderWithProviders } from '../test/render';
import type { ConsoleData } from '../data/context';
import { ApiError } from '../api/types';

describe('ProvidersPage', () => {
  it('shows a loading state before the registry resolves', async () => {
    const data = createMockData({ latency: 50 });
    renderWithProviders(<ProvidersPage />, { data });
    expect(screen.getByText(/loading providers/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/Lagos State Water/i)).toBeInTheDocument());
  });

  it('shows an empty state when there are no provider submissions', async () => {
    const data = createMockData();
    data.state.providers = [];
    renderWithProviders(<ProvidersPage />, { data });
    expect(await screen.findByText(/no provider submissions yet/i)).toBeInTheDocument();
  });

  it('shows an error state with a retry when the load fails', async () => {
    const data = createMockData();
    data.state.failNext = true;
    renderWithProviders(<ProvidersPage />, { data });
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not reach the api/i);
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('validates the provider form before submitting', async () => {
    const data = createMockData();
    const createProvider = vi.spyOn(data, 'createProvider');
    renderWithProviders(<ProvidersPage />, { data });
    await screen.findByText(/Lagos State Water/i);

    await userEvent.click(screen.getByRole('button', { name: /new provider/i }));
    await userEvent.click(screen.getByRole('button', { name: /create provider/i }));

    expect(await screen.findByText(/enter the provider name/i)).toBeInTheDocument();
    expect(screen.getByText(/enter an operational contact email/i)).toBeInTheDocument();
    expect(createProvider).not.toHaveBeenCalled();
  });

  it('creates a provider and surfaces it in the table', async () => {
    const data = createMockData();
    renderWithProviders(<ProvidersPage />, { data });
    await screen.findByText(/Lagos State Water/i);

    await userEvent.click(screen.getByRole('button', { name: /new provider/i }));
    await userEvent.type(screen.getByLabelText(/legal name/i), 'Kano Metropolis Water Board');
    await userEvent.type(screen.getByLabelText(/operational contact/i), 'ops@kano.example.ng');
    await userEvent.click(screen.getByRole('button', { name: /create provider/i }));

    expect(await screen.findByText(/Kano Metropolis Water Board/i)).toBeInTheDocument();
  });

  it('shows a submitting state and records an approval decision', async () => {
    const data = createMockData();
    renderWithProviders(<ProvidersPage />, { data });
    await screen.findByText(/capabilities pending review/i);
    await screen.findByText(/Electricity meter token/i);

    const approveButtons = screen.getAllByRole('button', { name: /^approve$/i });
    await userEvent.click(approveButtons[0]!);
    await userEvent.click(screen.getByRole('button', { name: /^approve$/i }));

    await waitFor(() =>
      expect(screen.queryByText(/Electricity meter token/i)).not.toBeInTheDocument(),
    );
  });

  it('requires a reason before recording a rejection', async () => {
    const data = createMockData();
    renderWithProviders(<ProvidersPage />, { data });
    await screen.findByText(/capabilities pending review/i);

    await userEvent.click(screen.getAllByRole('button', { name: /^reject$/i })[0]!);
    await userEvent.click(screen.getByRole('button', { name: /^reject$/i }));

    expect(await screen.findByText(/give a reason for this decision/i)).toBeInTheDocument();
  });

  it('blocks a reviewer role that is not permitted', async () => {
    const data = createMockData();
    renderWithProviders(<ProvidersPage />, {
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
      renderWithProviders(<ProvidersPage />, { data });
      await screen.findByText(/Lagos State Water/i);
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
    renderWithProviders(<ProvidersPage />, { data });
    await screen.findByText(/capabilities pending review/i);

    await userEvent.click(screen.getByRole('button', { name: /new provider/i }));
    await userEvent.type(screen.getByLabelText(/legal name/i), 'Dup');
    await userEvent.type(screen.getByLabelText(/operational contact/i), 'a@b.ng');
    await userEvent.click(screen.getByRole('button', { name: /create provider/i }));

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
  });
});
