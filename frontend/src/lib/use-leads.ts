"use client";

/**
 * TanStack Query hooks for the Leads list (first migration slice).
 *
 * Replaces the hand-rolled `useEffect` + `useState` fetch/pagination/delete
 * dance in `leads/page.tsx`. The cursor list becomes an `useInfiniteQuery`,
 * tag enrichment a dependent query, and delete a `useMutation` that
 * invalidates the list. Auth stays cookie-based — `getToken()` returns a
 * sentinel string used only to gate `enabled` and satisfy the api signatures.
 */

import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api, type EntityTags, type Lead, type Page, type Tag } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const leadsKeys = {
  all: ["leads"] as const,
  list: (q: string) => ["leads", "list", { q }] as const,
  tags: (ids: string[]) => ["leads", "tags", ids] as const,
};

/** Cursor-paginated leads list, optionally filtered by a search string. */
export function useLeadsInfinite(q: string) {
  const token = getToken();
  return useInfiniteQuery<Page<Lead>>({
    queryKey: leadsKeys.list(q),
    enabled: !!token,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      api.listLeads(token as string, {
        q: q || undefined,
        cursor: pageParam as string | undefined,
      }),
    getNextPageParam: (last) => (last.has_more ? (last.next_cursor ?? undefined) : undefined),
    // Keep the current results on screen while a new search loads (no skeleton
    // flash on every keystroke) — matches the old hand-rolled behavior.
    placeholderData: keepPreviousData,
  });
}

/**
 * Tag chips for the currently loaded leads. Keyed on the id list so adding a
 * page refetches once for the widened set; non-critical, so failures resolve
 * to an empty map rather than surfacing an error.
 */
export function useLeadTags(ids: string[]) {
  const token = getToken();
  return useQuery<Record<string, Tag[]>>({
    queryKey: leadsKeys.tags(ids),
    enabled: !!token && ids.length > 0,
    queryFn: async () => {
      const rows: EntityTags[] = await api.listTagAssignments(token as string, "lead", ids);
      const map: Record<string, Tag[]> = {};
      for (const row of rows) map[row.entity_id] = row.tags;
      return map;
    },
    // Keep prior chips visible while a widened id-set (after "load more")
    // refetches, instead of blanking every row's tags.
    placeholderData: keepPreviousData,
  });
}

/** Soft-delete a lead, then invalidate every leads list so it drops out. */
export function useDeleteLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteLead(getToken() as string, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: leadsKeys.all }),
  });
}
