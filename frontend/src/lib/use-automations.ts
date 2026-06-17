"use client";

/**
 * TanStack Query hooks for Automations: the rules list, the run log, and
 * create/update/delete mutations. All mutations invalidate the whole
 * automations key (rules + runs).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AutomationRule, type AutomationRun } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const automationsKeys = {
  all: ["automations"] as const,
  rules: ["automations", "rules"] as const,
  runs: ["automations", "runs"] as const,
};

export function useAutomations() {
  const token = getToken();
  return useQuery<AutomationRule[]>({
    queryKey: automationsKeys.rules,
    enabled: !!token,
    queryFn: () => api.listAutomations(token as string),
  });
}

export function useAutomationRuns() {
  const token = getToken();
  return useQuery<AutomationRun[]>({
    queryKey: automationsKeys.runs,
    enabled: !!token,
    queryFn: () => api.listAutomationRuns(token as string),
  });
}

export function useCreateAutomation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Parameters<typeof api.createAutomation>[1]) =>
      api.createAutomation(getToken() as string, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: automationsKeys.all }),
  });
}

export function useUpdateAutomation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof api.updateAutomation>[2] }) =>
      api.updateAutomation(getToken() as string, id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: automationsKeys.all }),
  });
}

export function useDeleteAutomation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteAutomation(getToken() as string, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: automationsKeys.all }),
  });
}
