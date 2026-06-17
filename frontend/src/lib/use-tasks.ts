"use client";

/**
 * TanStack Query hooks for the Tasks list. Offset-paginated (the API returns a
 * plain array, not a cursor envelope). Status toggles patch a single task in
 * place via setQueryData (keeps the optimistic-locking version fresh without a
 * full refetch); create/delete change the list size so they invalidate.
 */

import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api, type Task } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const TASKS_PAGE = 50;

export const tasksKeys = {
  all: ["tasks"] as const,
  list: ["tasks", "list"] as const,
};

/** Offset-paginated tasks list. */
export function useTasksInfinite() {
  const token = getToken();
  return useInfiniteQuery({
    queryKey: tasksKeys.list,
    enabled: !!token,
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      api.listTasks(token as string, { limit: TASKS_PAGE, offset: pageParam as number }),
    getNextPageParam: (last: Task[], all: Task[][]) =>
      last.length === TASKS_PAGE ? all.reduce((n, p) => n + p.length, 0) : undefined,
  });
}

export function useCreateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<Task>) => api.createTask(getToken() as string, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: tasksKeys.list }),
  });
}

/** Patch a task (status cycle); replaces it in place across the loaded pages. */
export function useUpdateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload, version }: { id: string; payload: Partial<Task>; version?: number }) =>
      api.updateTask(getToken() as string, id, payload, version),
    onSuccess: (updated) => {
      qc.setQueryData<{ pages: Task[][]; pageParams: unknown[] }>(tasksKeys.list, (old) =>
        old
          ? { ...old, pages: old.pages.map((pg) => pg.map((t) => (t.id === updated.id ? updated : t))) }
          : old,
      );
    },
  });
}

export function useDeleteTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteTask(getToken() as string, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: tasksKeys.list }),
  });
}
