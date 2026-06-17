"use client";

/**
 * TanStack Query hooks for the Customers list (migration slice 2).
 *
 * Mirrors `use-leads`: the cursor list becomes a `useInfiniteQuery`, tag
 * enrichment a dependent query, and delete a `useMutation` that invalidates
 * the list. Auth stays cookie-based — `getToken()` returns a sentinel used
 * only to gate `enabled` and satisfy the api signatures.
 */

import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api, type Customer, type Deal, type EntityTags, type Page, type Tag } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const customersKeys = {
  all: ["customers"] as const,
  list: (q: string) => ["customers", "list", { q }] as const,
  tags: (ids: string[]) => ["customers", "tags", ids] as const,
  detail: (id: string) => ["customers", "detail", id] as const,
  deals: (id: string) => ["customers", "deals", id] as const,
};

/** Cursor-paginated customers list, optionally filtered by a search string. */
export function useCustomersInfinite(q: string) {
  const token = getToken();
  return useInfiniteQuery<Page<Customer>>({
    queryKey: customersKeys.list(q),
    enabled: !!token,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      api.listCustomers(token as string, {
        q: q || undefined,
        cursor: pageParam as string | undefined,
      }),
    getNextPageParam: (last) => (last.has_more ? (last.next_cursor ?? undefined) : undefined),
    // Keep results on screen while a new search loads (no skeleton flash).
    placeholderData: keepPreviousData,
  });
}

/**
 * Tag chips for the currently loaded customers. Keyed on the id list so a new
 * page refetches once for the widened set; non-critical, so failures resolve
 * to an empty map rather than surfacing an error.
 */
export function useCustomerTags(ids: string[]) {
  const token = getToken();
  return useQuery<Record<string, Tag[]>>({
    queryKey: customersKeys.tags(ids),
    enabled: !!token && ids.length > 0,
    queryFn: async () => {
      const rows: EntityTags[] = await api.listTagAssignments(token as string, "customer", ids);
      const map: Record<string, Tag[]> = {};
      for (const row of rows) map[row.entity_id] = row.tags;
      return map;
    },
    // Keep prior chips visible while a widened id-set refetches.
    placeholderData: keepPreviousData,
  });
}

/** Soft-delete a customer, then invalidate every customers list so it drops out. */
export function useDeleteCustomer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteCustomer(getToken() as string, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: customersKeys.all }),
  });
}

// ── Detail page ───────────────────────────────────────────────────────────

/** Single customer by id (detail page read). */
export function useCustomer(id: string) {
  const token = getToken();
  return useQuery<Customer>({
    queryKey: customersKeys.detail(id),
    enabled: !!token,
    queryFn: () => api.getCustomer(token as string, id),
  });
}

/** Deals linked to a customer (detail sidebar); non-critical. */
export function useCustomerDeals(id: string) {
  const token = getToken();
  return useQuery<Deal[]>({
    queryKey: customersKeys.deals(id),
    enabled: !!token,
    queryFn: () => api.listDeals(token as string, { customer_id: id }),
  });
}

/** Regenerate the AI summary; the updated customer replaces the cached detail. */
export function useSummarizeCustomer(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.summarizeCustomer(getToken() as string, id),
    onSuccess: (updated) => qc.setQueryData(customersKeys.detail(id), updated),
  });
}
