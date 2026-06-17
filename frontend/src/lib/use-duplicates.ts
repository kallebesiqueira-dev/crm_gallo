"use client";

/**
 * TanStack Query hooks for the Duplicates merge tool: list candidate groups
 * per entity type, and merge a group (which invalidates the list so the merged
 * group drops out).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type DuplicateEntity } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const duplicatesKeys = {
  all: ["duplicates"] as const,
  list: (entityType: DuplicateEntity) => ["duplicates", entityType] as const,
};

/** Duplicate candidate groups for an entity type. */
export function useDuplicates(entityType: DuplicateEntity) {
  const token = getToken();
  return useQuery({
    queryKey: duplicatesKeys.list(entityType),
    enabled: !!token,
    queryFn: () => api.listDuplicates(token as string, entityType),
  });
}

/** Merge a duplicate group; refreshes the candidate list on success. */
export function useMergeDuplicates() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Parameters<typeof api.mergeDuplicates>[1]) =>
      api.mergeDuplicates(getToken() as string, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: duplicatesKeys.all }),
  });
}
