// ORION — useApiData
//
// One fetch-with-states hook for the dashboard sections. docs/UI_DESIGN.md §9.12
// requires every data view to define loading, empty and error states, and four
// sections doing that by hand would drift: three would get a retry button and
// the fourth would silently render an empty table on a 500.
//
// Deliberately not a cache or a query library. It fetches once per mount, and
// again when `refresh` is called or a dependency changes.

import { useCallback, useEffect, useState } from 'react';

/**
 * useApiData(fetcher, deps)
 *
 * @param fetcher  () => Promise<any>   called on mount and on refresh
 * @param deps     array                re-fetch when these change
 *
 * Returns { data, loading, error, refresh }.
 */
export function useApiData(fetcher, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [nonce, setNonce] = useState(0);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    // A response arriving after the component unmounts, or after a newer
    // request was issued, must not overwrite current state.
    let live = true;

    setLoading(true);
    setError(null);

    Promise.resolve()
      .then(fetcher)
      .then((result) => {
        if (live) setData(result);
      })
      .catch((e) => {
        if (live) {
          setData(null);
          setError(e?.message || 'Request failed');
        }
      })
      .finally(() => {
        if (live) setLoading(false);
      });

    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { data, loading, error, refresh };
}

/** Normalise a list endpoint: some return a bare array, some wrap it. */
export function asList(data, key) {
  if (Array.isArray(data)) return data;
  if (data && key && Array.isArray(data[key])) return data[key];
  return [];
}

export default useApiData;
