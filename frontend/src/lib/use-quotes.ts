"use client";

/**
 * TanStack Query hook for the Quotes list. The list has no search/tags/delete
 * (those live on the detail page), so this is just a cursor list.
 */

import { useInfiniteQuery } from "@tanstack/react-query";
import { api, type Page, type Quote } from "@/lib/api";
import { getToken } from "@/lib/auth";

/** Cursor-paginated quotes list. */
export function useQuotesInfinite() {
  const token = getToken();
  return useInfiniteQuery<Page<Quote>>({
    queryKey: ["quotes", "list"],
    enabled: !!token,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      api.listQuotes(token as string, { cursor: pageParam as string | undefined }),
    getNextPageParam: (last) => (last.has_more ? (last.next_cursor ?? undefined) : undefined),
  });
}
