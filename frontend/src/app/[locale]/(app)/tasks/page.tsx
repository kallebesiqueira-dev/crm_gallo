"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle2, Circle, Loader2, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api, ApiError, type Task, type TaskPriority, type TaskStatus } from "@/lib/api";
import { getToken } from "@/lib/auth";

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

  async function refresh() {
    const token = getToken();
    if (!token) return;
    const list = await api.listTasks(token);
    setTasks(list);
  }

  useEffect(() => {
    refresh();
  }, []);

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
      <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("new")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={create} className="grid gap-3 sm:grid-cols-[1fr_auto_auto_auto]">
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t("placeholder")}
              required
            />
            <select
              aria-label="priority"
              className="flex h-10 rounded-md border border-input bg-background px-3 text-sm"
              value={priority}
              onChange={(e) => setPriority(e.target.value as TaskPriority)}
            >
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {t(`priorities.${p}`)}
                </option>
              ))}
            </select>
            <Input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className="sm:w-44"
            />
            <Button type="submit">
              <Plus className="h-4 w-4" />
              {t("add")}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {tasks.length === 0 ? (
            <div className="p-10 text-center text-sm text-muted-foreground">{t("empty")}</div>
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
                      <div className="text-xs text-muted-foreground">
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
    </div>
  );
}
