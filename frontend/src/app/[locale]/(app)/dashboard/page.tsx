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
  FileText,
  Plus,
  Target,
  TrendingUp,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type Company, type DashboardStats, type Quote, type Task } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DashboardCustomize } from "@/components/dashboard-customize";
import { OnboardingChecklistWidget } from "@/components/onboarding-checklist";
import { AssistantCard } from "@/components/assistant-card";

/**
 * GALLO CRM — premium dashboard, wired to REAL data. Light: white cards on a
 * soft tinted bg. Dark: landing-style purple/black gradient + glassmorphism.
 * KPIs, funnel, financial overview, quotes summary, my tasks and recent
 * clients all read live data from `api.stats` / tasks / companies. Never
 * demo numbers — empty widgets show a clean empty state.
 */
export default function DashboardPage() {
  const t = useTranslations("dashboard");
  const tStages = useTranslations("leads.stages");
  const tApp = useTranslations("app");
  const locale = useLocale();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api
      .stats(token)
      .then((s) => {
        setStats(s);
        setLoading(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Failed");
        setLoading(false);
      });
    api.listTasks(token, { mine: true }).then(setTasks).catch(() => {});
    api
      .listCompanies(token, { limit: 8 })
      .then((p) => setCompanies(p.items))
      .catch(() => {});
    api
      .listQuotes(token, { limit: 5 })
      .then((p) => setQuotes(p.items))
      .catch(() => {});
  }, []);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("dashboard-hidden");
      if (raw) setHidden(new Set(JSON.parse(raw) as string[]));
    } catch {
      /* ignore corrupt prefs */
    }
  }, []);

  function toggleSection(key: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      try {
        localStorage.setItem("dashboard-hidden", JSON.stringify([...next]));
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  const eur = useMemo(
    () => new Intl.NumberFormat(locale, { style: "currency", currency: "EUR", maximumFractionDigits: 0 }),
    [locale],
  );
  const int = useMemo(() => new Intl.NumberFormat(locale), [locale]);

  const openTasks = useMemo(() => tasks.filter((task) => task.status !== "done").slice(0, 6), [tasks]);

  // Per-currency breakdown under the EUR headline when the open
  // pipeline spans 2+ currencies (plan.md §6: display-only, no FX) —
  // e.g. "€10,000 · CHF 3,200". Single-currency orgs see no change.
  const currencyBreakdown = useMemo(() => {
    const byCurrency = stats?.pipeline_value_by_currency ?? {};
    const entries = Object.entries(byCurrency);
    if (entries.length < 2) return null;
    return entries
      .map(([code, amount]) =>
        new Intl.NumberFormat(locale, {
          style: "currency",
          currency: code,
          maximumFractionDigits: 0,
        }).format(amount),
      )
      .join(" · ");
  }, [stats, locale]);

  const kpis = [
    { label: t("totalLeads"), value: stats ? int.format(stats.total_leads) : "—", icon: Users },
    { label: t("totalDeals"), value: stats ? int.format(stats.total_deals) : "—", icon: Target },
    {
      label: t("pipelineValue"),
      value: stats ? eur.format(stats.pipeline_value_eur || 0) : "—",
      icon: TrendingUp,
      sub: currencyBreakdown,
    },
    {
      label: t("conversionRate"),
      value: stats ? `${(stats.conversion_rate * 100).toFixed(1)}%` : "—",
      icon: CheckCircle2,
    },
  ];

  const customizeItems = [
    { key: "activity", label: t("pipelineTasks") },
    { key: "clients", label: t("recentCompanies") },
  ];

  return (
    <div className="relative space-y-5">
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 -z-10 hidden bg-[radial-gradient(120%_120%_at_15%_0%,#1a1033_0%,#0d0a18_55%,#080611_100%)] dark:block"
      >
        <div className="absolute -left-[10%] top-[8%] h-[40rem] w-[40rem] rounded-full bg-[radial-gradient(closest-side,rgba(139,92,246,0.22),transparent_70%)] blur-3xl" />
        <div className="absolute -right-[12%] bottom-[0%] h-[40rem] w-[40rem] rounded-full bg-[radial-gradient(closest-side,rgba(217,70,239,0.16),transparent_70%)] blur-3xl" />
      </div>

      {/* Brand header + toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Image
            src="/gallo-logo.png"
            alt={tApp("name")}
            width={52}
            height={52}
            className="h-12 w-12 shrink-0 rounded-xl object-contain shadow-sm"
            priority
          />
          <div className="min-w-0">
            <div className="bg-gradient-to-r from-violet-600 to-fuchsia-500 bg-clip-text text-xl font-bold tracking-tight text-transparent dark:from-white dark:to-violet-200">
              GALLO crm
            </div>
            <div className="line-clamp-2 text-xs text-muted-foreground">{t("welcome")}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button asChild size="sm" className="gap-1.5">
            <Link href={`/${locale}/tasks`}>
              <Plus className="h-4 w-4" />
              <span>{t("newActivity")}</span>
            </Link>
          </Button>
          <DashboardCustomize items={customizeItems} hidden={hidden} onToggle={toggleSection} />
        </div>
      </div>

      <AssistantCard />

      {/* Onboarding checklist — visible until all 5 steps are done or dismissed */}
      <OnboardingChecklistWidget locale={locale} />

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map((k) => (
          <Panel key={k.label} className="p-5">
            <div className="flex items-start justify-between">
              <div className="text-sm font-medium text-muted-foreground">{k.label}</div>
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary">
                <k.icon className="h-5 w-5" />
              </span>
            </div>
            {loading ? (
              <Skeleton className="mt-3 h-9 w-24" />
            ) : (
              <div className="mt-3 text-3xl font-bold tracking-tight">{k.value}</div>
            )}
            {!loading && "sub" in k && k.sub ? (
              <div className="mt-1 text-xs text-muted-foreground">{k.sub}</div>
            ) : null}
          </Panel>
        ))}
      </div>

      {/* Pipeline funnel + my tasks ("recent activity" cut — it duplicated the Leads list;
          the financial block moved into Reports, skills.md §4) */}
      <div className={cn("grid grid-cols-1 gap-4 lg:grid-cols-2", hidden.has("activity") && "hidden")}>
        <Panel className="flex flex-col p-5">
          <SectionTitle icon={Target}>{t("pipeline")}</SectionTitle>
          <Funnel funnel={stats?.pipeline_funnel ?? []} tStages={tStages} eur={eur} empty={t("noData")} />
          <CardLink href={`/${locale}/pipeline`}>{t("goToPipeline")}</CardLink>
        </Panel>

        <Panel className="flex flex-col p-5">
          <SectionTitle icon={CalendarDays}>{t("myTasks")}</SectionTitle>
          {openTasks.length === 0 ? (
            <div className="grid flex-1 place-items-center py-8 text-xs text-muted-foreground">{t("noTasks")}</div>
          ) : (
            <div className="mt-3 space-y-1">
              {openTasks.map((task) => (
                <div key={task.id} className="flex items-center gap-3 rounded-lg px-2 py-2 transition hover:bg-accent">
                  <span className="h-4 w-4 shrink-0 rounded-full border-2 border-primary/50" />
                  <div className="min-w-0 flex-1 truncate text-sm">{task.title}</div>
                  {task.due_date && (
                    <div className="shrink-0 text-xs font-medium tabular-nums text-muted-foreground">
                      {new Date(task.due_date).toLocaleDateString(locale)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          <CardLink href={`/${locale}/tasks?view=month`}>{t("viewCalendar")}</CardLink>
        </Panel>
      </div>

      {/* Recent clients + documents */}
      <div className={cn("grid grid-cols-1 gap-4 lg:grid-cols-3", hidden.has("clients") && "hidden")}>
        <Panel className="p-5 lg:col-span-2">
          <div className="flex items-center justify-between">
            <SectionTitle icon={Building2}>{t("recentCompanies")}</SectionTitle>
            <CardLinkInline href={`/${locale}/companies`}>{t("viewAll")}</CardLinkInline>
          </div>
          {companies.length === 0 ? (
            <div className="grid place-items-center py-8 text-xs text-muted-foreground">{t("noData")}</div>
          ) : (
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {companies.slice(0, 4).map((c) => (
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

        <Panel className="p-5">
          <div className="flex items-center justify-between">
            <SectionTitle icon={FileText}>{t("recentDocuments")}</SectionTitle>
            <CardLinkInline href={`/${locale}/quotes`}>{t("viewAll")}</CardLinkInline>
          </div>
          {quotes.length === 0 ? (
            <div className="grid place-items-center py-10 text-center text-xs text-muted-foreground">
              {t("noDocuments")}
            </div>
          ) : (
            <div className="mt-3 space-y-1.5">
              {quotes.slice(0, 5).map((doc) => (
                <Link
                  key={doc.id}
                  href={`/${locale}/quotes/${doc.id}`}
                  className="flex items-center gap-2.5 rounded-lg border border-border bg-background/40 px-3 py-2 transition hover:border-primary/40"
                >
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{doc.number}</div>
                    <div className="truncate text-xs text-muted-foreground">{doc.title}</div>
                  </div>
                  <span
                    title={doc.status}
                    className={cn(
                      "h-2 w-2 shrink-0 rounded-full",
                      doc.status === "accepted"
                        ? "bg-emerald-500"
                        : doc.status === "sent"
                          ? "bg-blue-500"
                          : doc.status === "declined" || doc.status === "expired"
                            ? "bg-red-500"
                            : "bg-muted-foreground",
                    )}
                  />
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
        "dark:border-white/10 dark:bg-[#1d1545] dark:shadow-[0_8px_40px_-12px_rgba(139,92,246,0.25)]",
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

// Trapezoid funnel cone (bands connect into one smooth cone) + aligned data.
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
    return <div className="my-6 grid flex-1 place-items-center text-xs text-muted-foreground">{empty}</div>;
  }
  // Funnel: the stage NAME sits inside each band; bands go dark (Nuovo) → light
  // (Vinto) as deals advance; count + value align in fixed columns on the right.
  const widths = [100, 85, 70, 56, 44];
  return (
    <div className="my-4 mb-4 flex flex-col gap-1">
      {funnel.map((s, i) => (
        <div key={s.stage} className="flex items-center gap-2">
          <div className="flex min-w-0 flex-1 justify-center">
            <div
              className="flex h-8 max-w-full items-center justify-center truncate rounded px-2 text-center text-[11px] font-semibold text-white shadow-sm"
              style={{
                width: `${widths[i] ?? 44}%`,
                background: `linear-gradient(135deg, hsl(264 72% ${42 + i * 7}%), hsl(288 70% ${46 + i * 7}%))`,
              }}
            >
              {tStages(s.stage)}
            </div>
          </div>
          <span className="w-7 shrink-0 text-right text-xs font-semibold tabular-nums">{s.count}</span>
          <span className="w-20 shrink-0 whitespace-nowrap text-right text-[11px] text-muted-foreground tabular-nums">
            {eur.format(s.value_eur)}
          </span>
        </div>
      ))}
    </div>
  );
}
