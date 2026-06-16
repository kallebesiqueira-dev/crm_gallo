"use client";

/**
 * TanStack Query hook for the Contracts list. Like quotes, the list is just a
 * cursor list (no search/tags/delete — those live on the detail page).
 */

import { useInfiniteQuery } from "@tanstack/react-query";
import { api, type Contract, type Page } from "@/lib/api";
import { getToken } from "@/lib/auth";

/** Cursor-paginated contracts list. */
export function useContractsInfinite() {
  const token = getToken();
  return useInfiniteQuery<Page<Contract>>({
    queryKey: ["contracts", "list"],
    enabled: !!token,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      api.listContracts(token as string, { cursor: pageParam as string | undefined }),
    getNextPageParam: (last) => (last.has_more ? (last.next_cursor ?? undefined) : undefined),
  });
}
