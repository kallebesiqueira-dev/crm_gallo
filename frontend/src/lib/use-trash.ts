"use client";

/**
 * TanStack Query hooks for Trash. The list is offset-paginated (TrashPage
 * envelope, mixed entity types); tab badges come from /trash/counts. Restore /
 * hard-delete / empty all invalidate both the list and the counts.
 */

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api, type TrashCounts, type TrashItem, type TrashPage } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const TRASH_PAGE = 50;

export const trashKeys = {
  all: ["trash"] as const,
  list: ["trash", "list"] as const,
  counts: ["trash", "counts"] as const,
};

/** Offset-paginated trash list (all entity types; filtered client-side by tab). */
export function useTrashInfinite() {
  const token = getToken();
  return useInfiniteQuery({
    queryKey: trashKeys.list,
    enabled: !!token,
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      api.listTrash(token as string, { limit: TRASH_PAGE, offset: pageParam as number }),
    getNextPageParam: (last: TrashPage, all: TrashPage[]) =>
      last.has_more ? all.reduce((n, p) => n + p.items.length, 0) : undefined,
  });
}

/** Exact per-type counts for the tab badges. */
export function useTrashCounts() {
  const token = getToken();
  return useQuery<TrashCounts>({
    queryKey: trashKeys.counts,
    enabled: !!token,
    queryFn: () => api.trashCounts(token as string),
  });
}

function useTrashMutation<TArgs>(fn: (args: TArgs) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => qc.invalidateQueries({ queryKey: trashKeys.all }),
  });
}

export function useRestoreFromTrash() {
  return useTrashMutation((a: { type: TrashItem["entity_type"]; id: string }) =>
    api.restoreFromTrash(getToken() as string, a.type, a.id),
  );
}

export function useHardDelete() {
  return useTrashMutation((a: { type: TrashItem["entity_type"]; id: string }) =>
    api.hardDelete(getToken() as string, a.type, a.id),
  );
}

export function useEmptyTrash() {
  return useTrashMutation((_: void) => api.emptyTrash(getToken() as string));
}
