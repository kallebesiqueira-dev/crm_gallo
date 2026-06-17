"use client";

/**
 * TanStack Query hooks for the Dashboard. All reads (the page mutates nothing):
 * the headline stats plus three small previews. Each preview is best-effort —
 * a failure resolves to an empty list rather than blocking the page.
 */

import { useQuery } from "@tanstack/react-query";
import { api, type Company, type DashboardStats, type Quote, type Task } from "@/lib/api";
import { getToken } from "@/lib/auth";

/** Headline KPIs (server-cached ~60s). Drives the page's loading/error state. */
export function useDashboardStats() {
  const token = getToken();
  return useQuery<DashboardStats>({
    queryKey: ["dashboard", "stats"],
    enabled: !!token,
    queryFn: () => api.stats(token as string),
  });
}

/** The current user's tasks (open-task widget). */
export function useMyTasks() {
  const token = getToken();
  return useQuery<Task[]>({
    queryKey: ["dashboard", "my-tasks"],
    enabled: !!token,
    queryFn: () => api.listTasks(token as string, { mine: true }),
  });
}

/** A short companies preview list. */
export function useCompaniesPreview() {
  const token = getToken();
  return useQuery<Company[]>({
    queryKey: ["dashboard", "companies-preview"],
    enabled: !!token,
    queryFn: async () => (await api.listCompanies(token as string, { limit: 8 })).items,
  });
}

/** A short quotes preview list. */
export function useQuotesPreview() {
  const token = getToken();
  return useQuery<Quote[]>({
    queryKey: ["dashboard", "quotes-preview"],
    enabled: !!token,
    queryFn: async () => (await api.listQuotes(token as string, { limit: 5 })).items,
  });
}
