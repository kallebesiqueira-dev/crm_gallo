"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";

/**
 * Reads a single query-string param and reports its current value to the
 * parent via `onValue`.
 *
 * Its only job is to quarantine `useSearchParams()`. In Next.js 15 any
 * client component that calls `useSearchParams()` opts the whole route out
 * of static prerendering unless it sits under a <Suspense> boundary —
 * otherwise `next build` fails with "useSearchParams() should be wrapped in
 * a suspense boundary". By isolating the hook here and wrapping THIS
 * component in <Suspense fallback={null}>, the host page keeps rendering
 * statically while the param is read on the client after hydration.
 *
 * Renders nothing. `onValue` must be referentially stable (a `useState`
 * setter, or a `useCallback`) so the effect doesn't re-fire every render.
 */
export function SearchParamWatcher({
  name,
  onValue,
}: {
  name: string;
  onValue: (value: string | null) => void;
}) {
  const search = useSearchParams();
  const value = search.get(name);
  useEffect(() => {
    onValue(value);
  }, [value, onValue]);
  return null;
}
