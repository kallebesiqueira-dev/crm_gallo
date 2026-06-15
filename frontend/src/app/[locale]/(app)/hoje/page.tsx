"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import {
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  Clock,
  ListTodo,
  PhoneCall,
  Timer,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  api,
  type DealTodayItem,
  type HojeResponse,
  type TaskTodayItem,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { ActionIcon } from "@/lib/action-icons";

function formatDatetime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function DealRow({ deal }: { deal: DealTodayItem }) {
  const locale = useLocale();
  return (
    <Link
      href={`/${locale}/pipeline/${deal.id}`}
      className="flex items-center justify-between rounded-lg border bg-card px-4 py-3 text-sm transition-colors hover:bg-muted/50"
    >
      <div className="min-w-0">
        <p className="truncate font-medium">{deal.title}</p>
        {deal.customer_name && (
          <p className="text-xs text-muted-foreground">{deal.customer_name}</p>
        )}
      </div>
      <div className="ml-4 shrink-0 text-right">
        {deal.next_action_type && (
          <ActionIcon
            type={deal.next_action_type}
            className="inline-block h-4 w-4 text-muted-foreground"
          />
        )}
        {deal.next_action_at && (
          <p className="text-xs text-muted-foreground">{formatDatetime(deal.next_action_at)}</p>
        )}
      </div>
    </Link>
  );
}

function TaskRow({ task, locale, onDone }: { task: TaskTodayItem; locale: string; onDone: (id: string) => void }) {
  const tHoje = useTranslations("hoje");
  const tPriorities = useTranslations("tasks.priorities");
  const [busy, setBusy] = useState(false);

  async function markDone(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    const token = getToken();
    if (!token || busy) return;
    setBusy(true);
    try {
      await api.updateTask(token, task.id, { status: "done" }, task.version);
      onDone(task.id);
    } catch {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2 rounded-lg border bg-card px-4 py-3 text-sm">
      <Button
        size="sm"
        variant="ghost"
        className="h-6 w-6 shrink-0 rounded-full p-0 text-muted-foreground hover:text-green-600"
        onClick={markDone}
        disabled={busy}
        title={tHoje("markDone")}
        aria-label={tHoje("markDone")}
      >
        <CheckCircle2 className="h-4 w-4" />
      </Button>
      <Link
        href={`/${locale}/tasks`}
        className="flex flex-1 items-center justify-between min-w-0 hover:text-primary transition-colors"
      >
        <div className="min-w-0">
          <p className="truncate font-medium">{task.title}</p>
          {task.customer_name && (
            <p className="text-xs text-muted-foreground">{task.customer_name}</p>
          )}
        </div>
        <div className="ml-3 shrink-0">
          <span
            className={cn(
              "rounded px-1.5 py-0.5 text-[10px] font-medium",
              task.priority === "high"
                ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                : task.priority === "medium"
                ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
            )}
          >
            {tPriorities(task.priority)}
          </span>
        </div>
      </Link>
    </div>
  );
}

function Section({
  title,
  icon: Icon,
  items,
  color,
  renderItem,
}: {
  title: string;
  icon: React.ElementType;
  items: unknown[];
  color: string;
  renderItem: (item: unknown, i: number) => React.ReactNode;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <div className={cn("mb-2 flex items-center gap-2 text-sm font-semibold", color)}>
        <Icon className="h-4 w-4" />
        <span>{title}</span>
        <span className="ml-auto rounded-full bg-current/10 px-2 py-0.5 text-xs font-normal opacity-70">
          {items.length}
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        {items.map((item, i) => renderItem(item, i))}
      </div>
    </div>
  );
}

export default function HojePage() {
  const t = useTranslations("hoje");
  const locale = useLocale();
  const [data, setData] = useState<HojeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function removeTask(id: string) {
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        today_tasks: prev.today_tasks.filter((t) => t.id !== id),
        overdue_tasks: prev.overdue_tasks.filter((t) => t.id !== id),
      };
    });
  }

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api
      .getHoje(token)
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Failed");
        setLoading(false);
      });
  }, []);

  const totalPending = data
    ? data.overdue_deals.length +
      data.today_deals.length +
      data.no_action_deals.length +
      data.overdue_tasks.length +
      data.today_tasks.length
    : 0;

  const allClear =
    !loading &&
    data &&
    totalPending === 0 &&
    data.stale_deals.length === 0;

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
          <CalendarClock className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          {!loading && !error && (
            <p className="text-sm text-muted-foreground">
              {allClear
                ? t("empty")
                : t("pendingCount", { count: totalPending })}
            </p>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      )}

      {allClear && (
        <div className="flex flex-col items-center gap-3 py-16 text-center text-muted-foreground">
          <CheckCircle2 className="h-12 w-12 text-green-500" />
          <p className="text-lg font-medium text-foreground">{t("empty")}</p>
        </div>
      )}

      {data && !allClear && (
        <div className="space-y-6">
          <Section
            title={t("overdueDeals")}
            icon={AlertCircle}
            items={data.overdue_deals}
            color="text-red-600"
            renderItem={(item, i) => <DealRow key={i} deal={item as DealTodayItem} />}
          />
          <Section
            title={t("todayDeals")}
            icon={CalendarClock}
            items={data.today_deals}
            color="text-amber-600"
            renderItem={(item, i) => <DealRow key={i} deal={item as DealTodayItem} />}
          />
          <Section
            title={t("overdueTasks")}
            icon={Timer}
            items={data.overdue_tasks}
            color="text-red-500"
            renderItem={(item, i) => <TaskRow key={i} task={item as TaskTodayItem} locale={locale} onDone={removeTask} />}
          />
          <Section
            title={t("todayTasks")}
            icon={ListTodo}
            items={data.today_tasks}
            color="text-blue-600"
            renderItem={(item, i) => <TaskRow key={i} task={item as TaskTodayItem} locale={locale} onDone={removeTask} />}
          />
          <Section
            title={t("noActionDeals")}
            icon={PhoneCall}
            items={data.no_action_deals}
            color="text-orange-500"
            renderItem={(item, i) => <DealRow key={i} deal={item as DealTodayItem} />}
          />
          <Section
            title={t("staleDeals")}
            icon={Clock}
            items={data.stale_deals}
            color="text-slate-500"
            renderItem={(item, i) => <DealRow key={i} deal={item as DealTodayItem} />}
          />
        </div>
      )}
    </div>
  );
}
