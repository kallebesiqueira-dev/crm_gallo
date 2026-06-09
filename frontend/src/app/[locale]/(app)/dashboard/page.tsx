"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useLocale, useTranslations } from "next-intl";
import {
  ArrowUpRight,
  Building2,
  CalendarDays,
  CheckCircle2,
  Target,
  TrendingUp,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type Company, type DashboardStats, type Lead, type Task } from "@/lib/api";
import { getToken } from "@/lib/auth";

/**
 * GALLO CRM — premium dashboard, wired to REAL data.
 *
 * Light: white cards on a soft tinted background, purple accents.
 * Dark: landing-style purple/black gradient + glassmorphism cards.
 *
 * Every widget reads live data: KPIs + funnel from `api.stats`, the 14-day
 * trend from leads, "my tasks" from `api.listTasks({mine})`, recent clients
 * from `api.listCompanies`. All copy is i18n (`dashboard` + `leads.stages`).
 */
export default function DashboardPage() {
  const t = useTranslations("dashboard");
  const tStages = useTranslations("leads.stages");
  const tApp = useTranslations("app");
  const locale = useLocale();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.stats(token).then(setStats).catch(() => {});
    api.listAllLeads(token).then(setLeads).catch(() => {});
    api.listTasks(token, { mine: true }).then(setTasks).catch(() => {});
    api
      .listCompanies(token, { limit: 8 })
      .then((p) => setCompanies(p.items))
      .catch(() => {});
  }, []);

  const eur = useMemo(
    () => new Intl.NumberFormat(locale, { style: "currency", currency: "EUR", maximumFractionDigits: 0 }),
    [locale],
  );
  const int = useMemo(() => new Intl.NumberFormat(locale), [locale]);

  const trend = useMemo(() => {
    const days: { label: string; count: number }[] = [];
    const today = new Date();
    for (let i = 13; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      days.push({
        label: `${d.getDate()}/${d.getMonth() + 1}`,
        count: leads.filter((l) => l.created_at.slice(0, 10) === key).length,
      });
    }
    return days;
  }, [leads]);

  const openTasks = useMemo(() => tasks.filter((task) => task.status !== "done").slice(0, 6), [tasks]);

  const kpis = [
    { label: t("totalLeads"), value: stats ? int.format(stats.total_leads) : "—", icon: Users },
    { label: t("totalDeals"), value: stats ? int.format(stats.total_deals) : "—", icon: Target },
    { label: t("pipelineValue"), value: stats ? eur.format(stats.pipeline_value_eur || 0) : "—", icon: TrendingUp },
    {
      label: t("conversionRate"),
      value: stats ? `${(stats.conversion_rate * 100).toFixed(1)}%` : "—",
      icon: CheckCircle2,
    },
  ];

  return (
    <div className="relative space-y-5">
      {/* Dark-mode ambient (landing-style) — light mode keeps the soft bg */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 -z-10 hidden bg-[radial-gradient(120%_120%_at_15%_0%,#1a1033_0%,#0d0a18_55%,#080611_100%)] dark:block"
      >
        <div className="absolute -left-[10%] top-[8%] h-[40rem] w-[40rem] rounded-full bg-[radial-gradient(closest-side,rgba(139,92,246,0.22),transparent_70%)] blur-3xl" />
        <div className="absolute -right-[12%] bottom-[0%] h-[40rem] w-[40rem] rounded-full bg-[radial-gradient(closest-side,rgba(217,70,239,0.16),transparent_70%)] blur-3xl" />
      </div>

      {/* Brand header */}
      <div className="flex items-center gap-3">
        <Image
          src="/icon.png"
          alt=""
          width={44}
          height={44}
          className="h-11 w-11 shrink-0 rounded-xl object-contain shadow-sm"
        />
        <div className="min-w-0">
          <div className="bg-gradient-to-r from-violet-600 to-fuchsia-500 bg-clip-text text-xl font-bold tracking-tight text-transparent dark:from-white dark:to-violet-200">
            {tApp("name")}
          </div>
          <div className="truncate text-xs text-muted-foreground">{t("welcome")}</div>
        </div>
      </div>

      {/* KPI row */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map((k) => (
          <Panel key={k.label} className="p-5">
            <div className="flex items-start justify-between">
              <div className="text-sm font-medium text-muted-foreground">{k.label}</div>
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary">
                <k.icon className="h-5 w-5" />
              </span>
            </div>
            <div className="mt-3 text-3xl font-bold tracking-tight">{k.value}</div>
          </Panel>
        ))}
      </div>

      {/* Trend + pipeline funnel */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel className="p-5 lg:col-span-2">
          <SectionTitle icon={TrendingUp}>{t("trend14Days")}</SectionTitle>
          {leads.length === 0 ? (
            <div className="grid h-44 place-items-center text-xs text-muted-foreground">{t("noData")}</div>
          ) : (
            <TrendBars data={trend} />
          )}
        </Panel>

        <Panel className="flex flex-col p-5">
          <SectionTitle icon={Target}>{t("pipeline")}</SectionTitle>
          <Funnel funnel={stats?.pipeline_funnel ?? []} tStages={tStages} eur={eur} empty={t("noData")} />
          <CardLink href={`/${locale}/pipeline`}>{t("goToPipeline")}</CardLink>
        </Panel>
      </div>

      {/* My tasks + recent clients */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel className="flex flex-col p-5">
          <SectionTitle icon={CalendarDays}>{t("myTasks")}</SectionTitle>
          {openTasks.length === 0 ? (
            <div className="grid flex-1 place-items-center py-8 text-xs text-muted-foreground">{t("noTasks")}</div>
          ) : (
            <div className="mt-3 space-y-1">
              {openTasks.map((task) => (
                <div key={task.id} className="flex items-center gap-3 rounded-lg px-2 py-2 transition hover:bg-accent">
                  <span className="h-4 w-4 shrink-0 rounded-full border-2 border-primary/50" />
                  <div className="flex-1 truncate text-sm">{task.title}</div>
                  {task.due_date && (
                    <div className="shrink-0 text-xs font-medium tabular-nums text-muted-foreground">
                      {new Date(task.due_date).toLocaleDateString(locale)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          <CardLink href={`/${locale}/tasks`}>{t("viewAll")}</CardLink>
        </Panel>

        <Panel className="p-5">
          <div className="flex items-center justify-between">
            <SectionTitle icon={Building2}>{t("recentCompanies")}</SectionTitle>
            <CardLinkInline href={`/${locale}/companies`}>{t("viewAll")}</CardLinkInline>
          </div>
          {companies.length === 0 ? (
            <div className="grid place-items-center py-8 text-xs text-muted-foreground">{t("noData")}</div>
          ) : (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {companies.slice(0, 6).map((c) => (
                <Link
                  key={c.id}
                  href={`/${locale}/companies/${c.id}`}
                  className="rounded-xl border border-border bg-background/40 p-3 transition hover:border-primary/40 hover:shadow-sm"
                >
                  <span className="grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 text-sm font-bold text-white">
                    {c.name.slice(0, 2).toUpperCase()}
                  </span>
                  <div className="mt-2 truncate text-sm font-semibold">{c.name}</div>
                  <div className="truncate text-xs text-muted-foreground">{c.industry ?? c.country ?? "—"}</div>
                </Link>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

/* ───────────────────────── primitives ───────────────────────── */

function Panel({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "rounded-2xl border bg-card shadow-sm",
        "border-border",
        "dark:border-white/10 dark:bg-white/[0.04] dark:backdrop-blur-xl dark:shadow-[0_8px_40px_-12px_rgba(139,92,246,0.25)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

function SectionTitle({ icon: Icon, children }: { icon: typeof Target; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-sm font-semibold">
      <Icon className="h-4 w-4 text-primary" />
      {children}
    </div>
  );
}

function CardLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="mt-auto block rounded-lg border border-border py-2 text-center text-xs font-semibold text-primary transition hover:bg-primary/5"
    >
      {children}
    </Link>
  );
}

function CardLinkInline({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline">
      {children} <ArrowUpRight className="h-3 w-3" />
    </Link>
  );
}

/* ───────────────────────── charts ───────────────────────── */

function TrendBars({ data }: { data: { label: string; count: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  return (
    <div className="mt-4 flex h-44 items-end gap-1.5">
      {data.map((d, i) => (
        <div key={i} className="flex flex-1 flex-col items-center gap-1">
          <div
            className="w-full rounded-t-md bg-gradient-to-t from-violet-600 to-fuchsia-400 transition-all hover:opacity-80"
            style={{ height: `${Math.max(2, (d.count / max) * 100)}%` }}
            title={`${d.label}: ${d.count}`}
          />
          <span className="text-[8px] text-muted-foreground">{d.label}</span>
        </div>
      ))}
    </div>
  );
}

function Funnel({
  funnel,
  tStages,
  eur,
  empty,
}: {
  funnel: { stage: string; count: number; value_eur: number }[];
  tStages: (key: string) => string;
  eur: Intl.NumberFormat;
  empty: string;
}) {
  if (!funnel.length) {
    return <div className="grid flex-1 place-items-center py-8 text-xs text-muted-foreground">{empty}</div>;
  }
  return (
    <div className="mt-4 space-y-1.5">
      {funnel.map((s, i) => (
        <div key={s.stage} className="flex items-center gap-3">
          <div className="flex flex-1 justify-center">
            <div
              className="truncate rounded-md px-2 py-1.5 text-center text-[11px] font-semibold text-white shadow-sm"
              style={{
                width: `${100 - i * 14}%`,
                background: `linear-gradient(90deg, hsl(262 83% ${64 - i * 6}%), hsl(290 80% ${66 - i * 6}%))`,
              }}
            >
              {tStages(s.stage)}
            </div>
          </div>
          <div className="w-10 shrink-0 text-right text-xs font-semibold tabular-nums">{s.count}</div>
          <div className="w-20 shrink-0 text-right text-[11px] text-muted-foreground tabular-nums">
            {eur.format(s.value_eur)}
          </div>
        </div>
      ))}
    </div>
  );
}
