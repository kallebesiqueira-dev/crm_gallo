"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/**
 * App-wide TanStack Query provider.
 *
 * The client is created once per browser session via `useState` (not a
 * module-level singleton) so it is never shared across requests during SSR
 * — each render tree gets its own cache, which is the React-Query SSR-safety
 * contract for the App Router.
 *
 * Defaults match this CRM's "fresh-enough" posture (cf. the 60s dashboard
 * cache): a short `staleTime` to coalesce duplicate fetches without making
 * data feel stale, and no refetch-on-focus (sales reps tab away constantly;
 * spurious refetches are noise, not value). Mutations invalidate explicitly.
 */
export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            gcTime: 5 * 60_000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
