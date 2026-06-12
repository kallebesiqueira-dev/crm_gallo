"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api, type Task, type TaskPriority } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

const PRIORITY_DOT: Record<TaskPriority, string> = {
  low: "bg-emerald-500",
  medium: "bg-amber-500",
  high: "bg-red-500",
};

const PRIORITY_VARIANT: Record<TaskPriority, "secondary" | "warning" | "danger"> = {
  low: "secondary",
  medium: "warning",
  high: "danger",
};

function startOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function buildGrid(month: Date): Date[] {
  const start = startOfMonth(month);
  const startDay = start.getDay(); // 0 = Sunday
  const grid: Date[] = [];
  // Pad to start with Monday-aligned grid; we'll keep Sunday-first for simplicity
  const firstCell = new Date(start);
  firstCell.setDate(firstCell.getDate() - startDay);
  for (let i = 0; i < 42; i++) {
    const d = new Date(firstCell);
    d.setDate(firstCell.getDate() + i);
    grid.push(d);
  }
  return grid;
}

function ymd(d: Date) {
  // Local-date YYYY-MM-DD; toISOString() shifts to UTC and can rotate the day.
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function CalendarPage() {
  const t = useTranslations("calendar");
  const tTasks = useTranslations("tasks");
  const locale = useLocale();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [cursor, setCursor] = useState<Date>(startOfMonth(new Date()));
  const [selected, setSelected] = useState<string>(ymd(new Date()));

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.listTasks(token).then(setTasks).catch(() => setTasks([]));
  }, []);

  const tasksByDate = useMemo(() => {
    const m = new Map<string, Task[]>();
    for (const tk of tasks) {
      if (!tk.due_date) continue;
      const key = tk.due_date.slice(0, 10);
      const arr = m.get(key) ?? [];
      arr.push(tk);
      m.set(key, arr);
    }
    return m;
  }, [tasks]);

  const grid = useMemo(() => buildGrid(cursor), [cursor]);
  const monthLabel = cursor.toLocaleDateString(locale, { month: "long", year: "numeric" });
  const today = ymd(new Date());
  const selectedTasks = tasksByDate.get(selected) ?? [];

  function prevMonth() {
    setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1));
  }
  function nextMonth() {
    setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1));
  }
  function goToday() {
    const now = new Date();
    setCursor(startOfMonth(now));
    setSelected(ymd(now));
  }

  const weekdays = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(2024, 0, 7 + i); // 2024-01-07 was a Sunday
    return d.toLocaleDateString(locale, { weekday: "short" });
  });

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="capitalize">{monthLabel}</CardTitle>
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" onClick={prevMonth} aria-label="previous">
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" onClick={goToday}>
                {t("today")}
              </Button>
              <Button variant="ghost" size="icon" onClick={nextMonth} aria-label="next">
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-7 gap-1 text-center text-xs uppercase tracking-wider text-muted-foreground">
            {weekdays.map((w) => (
              <div key={w} className="py-2">
                {w}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {grid.map((day) => {
              const key = ymd(day);
              const dayTasks = tasksByDate.get(key) ?? [];
              const inMonth = day.getMonth() === cursor.getMonth();
              const isToday = key === today;
              const isSelected = key === selected;
              return (
                <button
                  type="button"
                  key={key}
                  onClick={() => setSelected(key)}
                  className={cn(
                    "min-h-[72px] rounded-md border p-1 text-left transition-colors",
                    inMonth ? "bg-card" : "bg-muted/30 text-muted-foreground",
                    isSelected && "border-primary ring-2 ring-primary/30",
                    !isSelected && "hover:bg-accent",
                  )}
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className={cn(isToday && "rounded-full bg-primary px-1.5 text-primary-foreground")}>
                      {day.getDate()}
                    </span>
                    {dayTasks.length > 0 && (
                      <span className="text-[10px] text-muted-foreground">{dayTasks.length}</span>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-0.5">
                    {dayTasks.slice(0, 4).map((tk) => (
                      <span
                        key={tk.id}
                        className={cn("h-1.5 w-1.5 rounded-full", PRIORITY_DOT[tk.priority])}
                      />
                    ))}
                  </div>
                </button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {new Date(selected).toLocaleDateString(locale, {
              day: "numeric",
              month: "long",
              year: "numeric",
            })}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {selectedTasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("noTasksOnDay")}</p>
          ) : (
            <ul className="space-y-2">
              {selectedTasks.map((tk) => (
                <li
                  key={tk.id}
                  className="flex items-center justify-between gap-2 rounded-md border bg-card p-3"
                >
                  <div className="min-w-0">
                    <div
                      className={cn(
                        "truncate text-sm",
                        tk.status === "done" && "text-muted-foreground line-through",
                      )}
                    >
                      {tk.title}
                    </div>
                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                      {tk.status}
                    </div>
                  </div>
                  <Badge variant={PRIORITY_VARIANT[tk.priority]}>
                    {tTasks(`priorities.${tk.priority}`)}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
