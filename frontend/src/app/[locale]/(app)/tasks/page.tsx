"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  CalendarDays,
  CheckCircle2,
  Circle,
  ClipboardList,
  List,
  Loader2,
  Plus,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
import { TasksMonthView } from "@/components/tasks-month-view";
import { api, ApiError, type Task, type TaskPriority, type TaskStatus } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

type TasksView = "list" | "month";

const STATUSES: TaskStatus[] = ["todo", "in_progress", "done"];
const PRIORITIES: TaskPriority[] = ["low", "medium", "high"];

const STATUS_ICON: Record<TaskStatus, React.ReactNode> = {
  todo: <Circle className="h-4 w-4 text-muted-foreground" />,
  in_progress: <Loader2 className="h-4 w-4 text-primary" />,
  done: <CheckCircle2 className="h-4 w-4 text-emerald-500" />,
};

const PRIORITY_VARIANT: Record<TaskPriority, "secondary" | "warning" | "danger"> = {
  low: "secondary",
  medium: "warning",
  high: "danger",
};

export default function TasksPage() {
  const t = useTranslations("tasks");
  const tCommon = useTranslations("common");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState<TaskPriority>("medium");
  const [dueDate, setDueDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [view, setView] = useState<TasksView>("list");
  const PAGE = 50;

  // View mode: `?view=month` (the old /calendar deep link) wins, then the
  // last choice from localStorage. Read in an effect — no useSearchParams,
  // so the page needs no Suspense boundary.
  useEffect(() => {
    try {
      const fromUrl = new URLSearchParams(window.location.search).get("view");
      const stored = localStorage.getItem("tasks-view");
      const wanted = fromUrl ?? stored;
      if (wanted === "month" || wanted === "list") setView(wanted);
    } catch {
      /* stay on list */
    }
  }, []);

  function switchView(next: TasksView) {
    setView(next);
    try {
      localStorage.setItem("tasks-view", next);
      const url = new URL(window.location.href);
      url.searchParams.set("view", next);
      window.history.replaceState(null, "", url.toString());
    } catch {
      /* non-fatal: view still switches in-memory */
    }
  }

  async function refresh() {
    const token = getToken();
    if (!token) return;
    const list = await api.listTasks(token, { limit: PAGE });
    setTasks(list);
    setHasMore(list.length === PAGE);
    setLoading(false);
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadMore() {
    const token = getToken();
    if (!token || loadingMore) return;
    setLoadingMore(true);
    try {
      const more = await api.listTasks(token, { limit: PAGE, offset: tasks.length });
      setTasks((prev) => [...prev, ...more]);
      setHasMore(more.length === PAGE);
    } finally {
      setLoadingMore(false);
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    if (!token || !title.trim()) return;
    await api.createTask(token, {
      title: title.trim(),
      priority,
      due_date: dueDate || null,
    });
    setTitle("");
    setPriority("medium");
    setDueDate("");
    refresh();
  }

  async function cycleStatus(task: Task) {
    const token = getToken();
    if (!token) return;
    const next = STATUSES[(STATUSES.indexOf(task.status) + 1) % STATUSES.length];
    setError(null);
    try {
      const updated = await api.updateTask(token, task.id, { status: next }, task.version);
      setTasks((prev) => prev.map((t) => (t.id === task.id ? updated : t)));
    } catch (e) {
      if (e instanceof ApiError && e.status === 412) {
        // The task changed under us — surface a conflict and reload so
        // the row carries the fresh version for the next attempt.
        setError(tCommon("versionConflict"));
        refresh();
      } else {
        throw e;
      }
    }
  }

  async function remove(task: Task) {
    const token = getToken();
    if (!token) return;
    await api.deleteTask(token, task.id);
    setTasks((prev) => prev.filter((t) => t.id !== task.id));
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <div className="inline-flex rounded-md border p-0.5" role="tablist" aria-label={t("title")}>
          {(
            [
              { key: "list" as const, label: t("viewList"), icon: List },
              { key: "month" as const, label: t("viewMonth"), icon: CalendarDays },
            ]
          ).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={view === key}
              onClick={() => switchView(key)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium transition-colors",
                view === key
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("new")}</CardTitle>
        </CardHeader>
        <CardContent>
          {/* Mobile: stacked. Tablet: title on its own row, controls share one.
              Desktop: everything inline. */}
          <form onSubmit={create} className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:grid-cols-[1fr_auto_auto_auto]">
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t("placeholder")}
              required
              className="sm:col-span-3 lg:col-span-1"
            />
            <Select
              aria-label="priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value as TaskPriority)}
            >
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {t(`priorities.${p}`)}
                </option>
              ))}
            </Select>
            <Input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className="w-44 sm:w-full lg:w-44"
            />
            <Button type="submit">
              <Plus className="h-4 w-4" />
              {t("add")}
            </Button>
          </form>
        </CardContent>
      </Card>

      {view === "month" ? (
        <TasksMonthView />
      ) : (
        <>
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <ul className="divide-y">
              {Array.from({ length: 5 }).map((_, i) => (
                <li key={i} className="flex items-center gap-3 px-4 py-3">
                  <Skeleton className="h-4 w-4 shrink-0 rounded-full" />
                  <Skeleton className="h-4 flex-1" />
                  <Skeleton className="h-5 w-16 rounded-full" />
                </li>
              ))}
            </ul>
          ) : tasks.length === 0 ? (
            <EmptyState
              icon={ClipboardList}
              title={t("empty")}
            />
          ) : (
            <ul className="divide-y">
              {tasks.map((task) => (
                <li
                  key={task.id}
                  className="flex items-center gap-3 px-4 py-3 hover:bg-muted/30"
                >
                  <button
                    type="button"
                    onClick={() => cycleStatus(task)}
                    className="shrink-0"
                    aria-label="toggle status"
                  >
                    {STATUS_ICON[task.status]}
                  </button>
                  <div className="min-w-0 flex-1">
                    <div
                      className={`truncate text-sm ${
                        task.status === "done" ? "text-muted-foreground line-through" : ""
                      }`}
                    >
                      {task.title}
                    </div>
                    {task.due_date && (
                      <div
                        className={
                          task.status !== "done" && new Date(task.due_date) < new Date()
                            ? "text-xs font-medium text-red-600 dark:text-red-400"
                            : "text-xs text-muted-foreground"
                        }
                      >
                        {t("due")}: {new Date(task.due_date).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                  <Badge variant={PRIORITY_VARIANT[task.priority]}>
                    {t(`priorities.${task.priority}`)}
                  </Badge>
                  <button
                    type="button"
                    onClick={() => remove(task)}
                    className="shrink-0 text-muted-foreground hover:text-destructive"
                    aria-label="delete"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {hasMore && (
        <div className="flex justify-center">
          <Button type="button" variant="outline" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? <Loader2 className="h-4 w-4 animate-spin" /> : tCommon("loadMore")}
          </Button>
        </div>
      )}
        </>
      )}
    </div>
  );
}
