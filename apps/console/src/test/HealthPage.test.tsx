import { describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HealthPage } from '../views/HealthPage';
import { createMockData } from '../data/mockData';
import { renderWithProviders } from '../test/render';

describe('HealthPage', () => {
  it('renders health counts and quarantined capability', async () => {
    const data = createMockData();
    await renderWithProviders(<HealthPage />, { data });
    expect(await screen.findByText(/Cable TV subscription/i)).toBeInTheDocument();
    // Counts reflect the seeded capabilities: two healthy, one degraded, and one
    // quarantined (a quarantined capability is counted once, under quarantine,
    // not also under its unavailable health status).
    expect(screen.getByText(/2 healthy/i)).toBeInTheDocument();
    expect(screen.getByText(/1 degraded/i)).toBeInTheDocument();
    expect(screen.getByText(/0 unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/1 quarantined/i)).toBeInTheDocument();
  });

  it('filters the table by health state', async () => {
    const data = createMockData();
    await renderWithProviders(<HealthPage />, { data });
    await screen.findByText(/Cable TV subscription/i);

    await userEvent.selectOptions(screen.getByLabelText(/filter by health/i), 'degraded');
    await waitFor(() =>
      expect(screen.queryByText(/Cable TV subscription/i)).not.toBeInTheDocument(),
    );
    expect(screen.getByText(/Water bill payment \(schema 2.2.0\)/i)).toBeInTheDocument();
  });

  it('offers restore for a quarantined capability and applies it', async () => {
    const data = createMockData();
    await renderWithProviders(<HealthPage />, { data });
    await screen.findByText(/Cable TV subscription/i);

    await userEvent.click(screen.getByRole('button', { name: /restore/i }));
    await userEvent.type(screen.getByLabelText(/reason/i), 'Health check passes after the fix.');
    await userEvent.click(screen.getByRole('button', { name: /^approve$/i }));

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /restore/i })).not.toBeInTheDocument(),
    );
  });

  it('shows an empty state when the filter matches nothing', async () => {
    const data = createMockData();
    data.state.capabilities = [];
    await renderWithProviders(<HealthPage />, { data });
    expect(await screen.findByText(/no capabilities in this state/i)).toBeInTheDocument();
  });
});
