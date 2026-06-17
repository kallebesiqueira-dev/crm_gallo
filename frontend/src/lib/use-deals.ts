"use client";

/**
 * TanStack Query hooks for the Deal detail page. (The pipeline list is a
 * kanban with its own state, so there's no list hook here yet.)
 *
 * Deals use optimistic locking: PATCH/move/next-action take an `If-Match`
 * version. The mutations read the current version straight from the query
 * cache, so callers don't have to thread it through — and `setQueryData`
 * stores the server's bumped-version entity for the next mutation.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Deal, type NextActionType } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const dealsKeys = {
  all: ["deals"] as const,
  detail: (id: string) => ["deals", "detail", id] as const,
};

/** Single deal by id (detail page read). */
export function useDeal(id: string) {
  const token = getToken();
  return useQuery<Deal>({
    queryKey: dealsKeys.detail(id),
    enabled: !!token,
    queryFn: () => api.getDeal(token as string, id),
  });
}

/** Patch a deal (e.g. stage); version comes from the cached detail. */
export function useUpdateDeal(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<Deal>) => {
      const current = qc.getQueryData<Deal>(dealsKeys.detail(id));
      return api.updateDeal(getToken() as string, id, payload, current?.version);
    },
    onSuccess: (updated) => qc.setQueryData(dealsKeys.detail(id), updated),
  });
}

/** Schedule/clear a deal's follow-up; version comes from the cached detail. */
export function useSetNextAction(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      next_action_type: NextActionType | null;
      next_action_at: string | null;
    }) => {
      const current = qc.getQueryData<Deal>(dealsKeys.detail(id));
      return api.setNextAction(getToken() as string, id, body, current?.version);
    },
    onSuccess: (updated) => qc.setQueryData(dealsKeys.detail(id), updated),
  });
}

/** Soft-delete a deal (the page navigates away afterwards). */
export function useDeleteDeal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteDeal(getToken() as string, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: dealsKeys.all }),
  });
}
