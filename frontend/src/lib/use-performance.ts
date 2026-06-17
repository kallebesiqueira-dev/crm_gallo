"use client";

/**
 * TanStack Query hooks for the Performance screen: the summary (per period),
 * the goals list, and create/delete-goal mutations (which invalidate goals).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type GoalPeriod, type PerformanceSummary, type SalesGoal } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const performanceKeys = {
  all: ["performance"] as const,
  summary: (period: GoalPeriod) => ["performance", "summary", period] as const,
  goals: ["performance", "goals"] as const,
};

/** KPI/leaderboard/funnel summary for a period. */
export function usePerformanceSummary(period: GoalPeriod) {
  const token = getToken();
  return useQuery<PerformanceSummary>({
    queryKey: performanceKeys.summary(period),
    enabled: !!token,
    queryFn: () => api.performanceSummary(token as string, period),
  });
}

/** Sales goals with attainment. */
export function useGoals() {
  const token = getToken();
  return useQuery<SalesGoal[]>({
    queryKey: performanceKeys.goals,
    enabled: !!token,
    queryFn: () => api.listGoals(token as string),
  });
}

export function useCreateGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Parameters<typeof api.createGoal>[1]) =>
      api.createGoal(getToken() as string, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: performanceKeys.goals }),
  });
}

export function useDeleteGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteGoal(getToken() as string, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: performanceKeys.goals }),
  });
}
