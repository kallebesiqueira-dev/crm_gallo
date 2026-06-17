"use client";

/**
 * TanStack Query hooks for Web Forms (lead-capture): list + create/update/
 * delete. Mutations invalidate the list.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type WebForm } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const formsKeys = {
  all: ["forms"] as const,
  list: ["forms", "list"] as const,
};

export function useForms() {
  const token = getToken();
  return useQuery<WebForm[]>({
    queryKey: formsKeys.list,
    enabled: !!token,
    queryFn: () => api.listForms(token as string),
  });
}

export function useCreateForm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Parameters<typeof api.createForm>[1]) =>
      api.createForm(getToken() as string, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: formsKeys.list }),
  });
}

export function useUpdateForm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof api.updateForm>[2] }) =>
      api.updateForm(getToken() as string, id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: formsKeys.list }),
  });
}

export function useDeleteForm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteForm(getToken() as string, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: formsKeys.list }),
  });
}
