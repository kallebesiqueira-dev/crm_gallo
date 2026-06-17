"use client";

/**
 * TanStack Query hooks for the Companies list. Mirrors `use-customers`:
 * cursor list → useInfiniteQuery, tag chips → dependent query, delete →
 * mutation that invalidates the list.
 */

import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api, type Company, type CompanyRollup, type EntityTags, type Page, type Tag } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const companiesKeys = {
  all: ["companies"] as const,
  list: (q: string) => ["companies", "list", { q }] as const,
  tags: (ids: string[]) => ["companies", "tags", ids] as const,
  detail: (id: string) => ["companies", "detail", id] as const,
};

/** Cursor-paginated companies list, optionally filtered by a search string. */
export function useCompaniesInfinite(q: string) {
  const token = getToken();
  return useInfiniteQuery<Page<Company>>({
    queryKey: companiesKeys.list(q),
    enabled: !!token,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      api.listCompanies(token as string, {
        q: q || undefined,
        cursor: pageParam as string | undefined,
      }),
    getNextPageParam: (last) => (last.has_more ? (last.next_cursor ?? undefined) : undefined),
    placeholderData: keepPreviousData,
  });
}

/** Tag chips for the currently loaded companies (non-critical enrichment). */
export function useCompanyTags(ids: string[]) {
  const token = getToken();
  return useQuery<Record<string, Tag[]>>({
    queryKey: companiesKeys.tags(ids),
    enabled: !!token && ids.length > 0,
    queryFn: async () => {
      const rows: EntityTags[] = await api.listTagAssignments(token as string, "company", ids);
      const map: Record<string, Tag[]> = {};
      for (const row of rows) map[row.entity_id] = row.tags;
      return map;
    },
    placeholderData: keepPreviousData,
  });
}

/** Soft-delete a company, then invalidate every companies list so it drops out. */
export function useDeleteCompany() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteCompany(getToken() as string, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: companiesKeys.all }),
  });
}

/** Company detail rollup (company + linked customers/leads/deals). */
export function useCompanyRollup(id: string) {
  const token = getToken();
  return useQuery<CompanyRollup>({
    queryKey: companiesKeys.detail(id),
    enabled: !!token,
    queryFn: () => api.getCompanyRollup(token as string, id),
  });
}
