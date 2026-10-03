import { useCallback, useEffect, useState } from 'react';
import { ApiError, type Capability, type Provider } from '../api/types';
import { useData } from '../data/context';

export interface RegistryState {
  status: 'loading' | 'success' | 'error';
  error: ApiError | null;
  providers: Provider[];
  capabilities: Capability[];
  reload: () => Promise<void>;
  /** Runs a mutation and refreshes the working set; rethrows for the caller. */
  run: <T>(action: () => Promise<T>) => Promise<T>;
}

/**
 * Loads the provider registry working set. The frozen registry exposes create,
 * read, and review but no list endpoint, so the console derives its tables from
 * the data layer's session working set and refreshes after each mutation.
 */
export function useRegistry(): RegistryState {
  const data = useData();
  const [status, setStatus] = useState<RegistryState['status']>('loading');
  const [error, setError] = useState<ApiError | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [capabilities, setCapabilities] = useState<Capability[]>([]);

  const reload = useCallback(async () => {
    setStatus('loading');
    setError(null);
    try {
      const [nextProviders, nextCapabilities] = await Promise.all([
        data.listProviders(),
        data.listCapabilities(),
      ]);
      setProviders(nextProviders);
      setCapabilities(nextCapabilities);
      setStatus('success');
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, 'unknown_error', 'Load failed.'));
      setStatus('error');
    }
  }, [data]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const run = useCallback(
    async <T,>(action: () => Promise<T>): Promise<T> => {
      const result = await action();
      await reload();
      return result;
    },
    [reload],
  );

  return { status, error, providers, capabilities, reload, run };
}
