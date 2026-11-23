import { useCallback, useEffect, useRef, useState } from "react";

import { HttpError } from "./api";

/** Loads data for the current key; ignores answers that arrive after the key changed. */
export function useData<T>(load: (refresh: boolean) => Promise<T>, key: string) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [failure, setFailure] = useState<number | "network" | null>(null);
  const [loading, setLoading] = useState(true);
  const current = useRef(0);

  const run = useCallback(
    (refresh: boolean) => {
      const id = ++current.current;
      setLoading(true);
      setFailure(null);
      if (!refresh) setData(undefined);
      load(refresh)
        .then((d) => {
          if (id === current.current) setData(d);
        })
        .catch((e: unknown) => {
          if (id === current.current) setFailure(e instanceof HttpError ? e.status : "network");
        })
        .finally(() => {
          if (id === current.current) setLoading(false);
        });
    },
    // Reload only when the page key (app, range) changes; `load` is a new closure on every render.
    [key],
  );

  useEffect(() => run(false), [run]);

  return { data, failure, loading, reload: () => run(false), refresh: () => run(true) };
}
