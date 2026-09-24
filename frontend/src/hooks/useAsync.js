import { useCallback, useEffect, useRef, useState } from 'react';

const cache = new Map();

/**
 * Fetch data with loading/error state. `key` (string) enables a short
 * in-memory cache so revisiting a page renders instantly while refreshing.
 */
export function useAsync(fn, deps = [], { key, ttl = 30000, enabled = true } = {}) {
  const cached = key ? cache.get(key) : null;
  const [data, setData] = useState(cached?.data ?? null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(enabled && !cached);
  const seq = useRef(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const run = useCallback(
    async ({ silent = false } = {}) => {
      const id = ++seq.current;
      if (!silent) setLoading(true);
      try {
        const result = await fnRef.current();
        if (id === seq.current) {
          setData(result);
          setError(null);
          if (key) cache.set(key, { data: result, at: Date.now() });
        }
        return result;
      } catch (err) {
        if (id === seq.current) setError(err);
        return undefined;
      } finally {
        if (id === seq.current) setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key],
  );

  useEffect(() => {
    if (!enabled) return;
    const entry = key ? cache.get(key) : null;
    if (entry) {
      setData(entry.data);
      setLoading(false);
      if (Date.now() - entry.at < ttl) return;
      run({ silent: true });
      return;
    }
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled]);

  return { data, error, loading, refetch: run, setData };
}

export function invalidateCache(prefix = '') {
  for (const k of cache.keys()) if (k.startsWith(prefix)) cache.delete(k);
}
