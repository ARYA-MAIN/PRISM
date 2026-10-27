import { useCallback, useEffect, useState } from 'react';
import { apiRequest } from '../lib/api';

export function useApi<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const reload = useCallback(() => setReloadKey((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    apiRequest<T>(path)
      .then((value) => { if (active) setData(value); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'Request failed.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path, reloadKey]);

  return { data, loading, error, reload, setData };
}
