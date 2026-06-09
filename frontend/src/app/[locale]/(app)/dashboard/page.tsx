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
  ChevronDown,
  FileText,
  Settings2,
  Target,
  TrendingUp,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type Company, type DashboardStats, type Lead, type Task } from "@/lib/api";
import { getToken } from "@/lib/auth";

/**
 * GALLO CRM — premium dashboard, wired to REAL data. Light: white cards on a
 * soft tinted bg. Dark: landing-style purple/black gradient + glassmorphism.
 * KPIs, funnel, financial overview, quotes summary, recent activity, my tasks
 * and recent clients all read live data from `api.stats` / leads / tasks /
 * companies. Never demo numbers — empty widgets show a clean empty state.
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
  const eur2 = useMemo(
    () => new Intl.NumberFormat(locale, { style: "currency", currency: "EUR", minimumFractionDigits: 2 }),
    [locale],
  );
  const int = useMemo(() => new Intl.NumberFormat(locale), [locale]);

  const recentLeads = useMemo(
    () => [...leads].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 4),
    [leads],
  );
  const openTasks = useMemo(() => tasks.filter((task) => task.status !== "done").slice(0, 6), [tasks]);

  const q = stats?.quotes;
  const openTotal = (q?.open_eur ?? 0) + (q?.overdue_eur ?? 0);
  const openPct = openTotal > 0 ? Math.round(((q?.open_eur ?? 0) / openTotal) * 100) : 0;

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
              {tApp("name")}
            </div>
            <div className="truncate text-xs text-muted-foreground">{t("welcome")}</div>
          </div>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium text-foreground shadow-sm transition hover:border-primary/40"
        >
          <Settings2 className="h-4 w-4 text-primary" />
          {t("customize")}
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </button>
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

      {/* Financial overview + quotes */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel className="p-5 lg:col-span-2">
          <SectionTitle icon={TrendingUp}>{t("financialOverview")}</SectionTitle>
          <div className="mt-4 grid gap-6 md:grid-cols-[1.5fr_1fr]">
            <div>
              <div className="text-xs text-muted-foreground">{t("payments")}</div>
              <div className="text-sm font-semibold">
                {t("total")} {eur2.format(stats?.revenue_total_eur ?? 0)}
              </div>
              <PaymentsBars data={stats?.monthly_revenue ?? []} locale={locale} />
            </div>
            <div className="md:border-l md:border-border md:pl-5">
              <div className="text-xs text-muted-foreground">{t("openAmounts")}</div>
              <DonutOpen pct={openPct} />
              <div className="mt-3 space-y-1.5 text-xs">
                <LegendRow color="bg-violet-500" label={t("openLabel")} value={eur2.format(q?.open_eur ?? 0)} />
                <LegendRow color="bg-rose-500" label={t("overdue")} value={eur2.format(q?.overdue_eur ?? 0)} />
              </div>
            </div>
          </div>
        </Panel>

        <Panel className="p-5">
          <SectionTitle icon={FileText}>{t("quotesTitle")}</SectionTitle>
          <div className="mt-2 text-xs text-muted-foreground">{t("totalOffered")}</div>
          <div className="text-lg font-bold">{eur2.format(q?.total_eur ?? 0)}</div>
          <div className="mt-2 flex items-center gap-4">
            <CitazioniRings q={q} />
            <div className="flex-1 space-y-2 text-xs">
              <LegendRow color="bg-violet-500" label={t("outstanding")} value={eur2.format(q?.outstanding_eur ?? 0)} />
              <LegendRow color="bg-fuchsia-500" label={t("accepted")} value={eur2.format(q?.accepted_eur ?? 0)} />
              <LegendRow color="bg-rose-400" label={t("rejected")} value={eur2.format(q?.rejected_eur ?? 0)} />
            </div>
          </div>
        </Panel>
      </div>

      {/* Recent activity + pipeline funnel + my tasks */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel className="flex flex-col p-5">
          <SectionTitle icon={CheckCircle2}>{t("recentActivities")}</SectionTitle>
          {recentLeads.length === 0 ? (
            <div className="grid flex-1 place-items-center py-8 text-xs text-muted-foreground">{t("noData")}</div>
          ) : (
            <div className="mt-3 space-y-1">
              {recentLeads.map((l) => (
                <Link
                  key={l.id}
                  href={`/${locale}/leads/${l.id}`}
                  className="flex items-center gap-3 rounded-lg px-2 py-2 transition hover:bg-accent"
                >
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                    <Users className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">
                      {l.first_name} {l.last_name}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">{tStages(l.stage)}</div>
                  </div>
                  <div className="shrink-0 text-[11px] text-muted-foreground">
                    {new Date(l.created_at).toLocaleDateString(locale)}
                  </div>
                </Link>
              ))}
            </div>
          )}
          <CardLink href={`/${locale}/leads`}>{t("viewAll")}</CardLink>
        </Panel>

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
          <CardLink href={`/${locale}/tasks`}>{t("viewCalendar")}</CardLink>
        </Panel>
      </div>

      {/* Recent clients + documents */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel className="p-5 lg:col-span-2">
          <div className="flex items-center justify-between">
            <SectionTitle icon={Building2}>{t("recentCompanies")}</SectionTitle>
            <CardLinkInline href={`/${locale}/companies`}>{t("viewAll")}</CardLinkInline>
          </div>
          {companies.length === 0 ? (
            <div className="grid place-items-center py-8 text-xs text-muted-foreground">{t("noData")}</div>
          ) : (
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
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
          <div className="grid place-items-center py-10 text-center text-xs text-muted-foreground">
            {t("noDocuments")}
          </div>
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

function LegendRow({ color, label, value }: { color: string; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-2 text-muted-foreground">
        <span className={cn("h-2.5 w-2.5 rounded-full", color)} />
        {label}
      </span>
      <span className="font-semibold text-foreground">{value}</span>
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

function PaymentsBars({ data, locale }: { data: { month: string; value_eur: number }[]; locale: string }) {
  const max = Math.max(1, ...data.map((d) => d.value_eur));
  const fmt = (m: string) => {
    const d = new Date(`${m}-01T00:00:00`);
    return Number.isNaN(d.getTime()) ? m.slice(5) : d.toLocaleDateString(locale, { month: "short" });
  };
  return (
    <div className="mt-3 flex h-36 items-end gap-1.5">
      {data.map((d) => (
        <div key={d.month} className="flex flex-1 flex-col items-center gap-1">
          <div
            className="w-full rounded-t-md bg-gradient-to-t from-violet-600 to-fuchsia-400 transition-all hover:opacity-80"
            style={{ height: `${Math.max(2, (d.value_eur / max) * 100)}%` }}
            title={`${d.month}: ${d.value_eur}`}
          />
          <span className="text-[9px] text-muted-foreground">{fmt(d.month)}</span>
        </div>
      ))}
    </div>
  );
}

function DonutOpen({ pct }: { pct: number }) {
  const r = 42;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative mx-auto mt-3 grid h-32 w-32 place-items-center">
      <svg viewBox="0 0 100 100" className="absolute inset-0 -rotate-90">
        <circle cx="50" cy="50" r={r} fill="none" stroke="currentColor" strokeWidth="12" className="text-primary/10" />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke="url(#donutOpen)"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * c} ${c}`}
        />
        <defs>
          <linearGradient id="donutOpen" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#8b5cf6" />
            <stop offset="100%" stopColor="#d946ef" />
          </linearGradient>
        </defs>
      </svg>
      <div className="text-2xl font-bold text-primary">{pct}%</div>
    </div>
  );
}

function CitazioniRings({ q }: { q?: DashboardStats["quotes"] }) {
  const total = q?.total_eur ?? 0;
  const frac = (v: number) => (total > 0 ? v / total : 0);
  const rings = [
    { r: 40, color: "#8b5cf6", f: frac(q?.outstanding_eur ?? 0) },
    { r: 31, color: "#d946ef", f: frac(q?.accepted_eur ?? 0) },
    { r: 22, color: "#fb7185", f: frac(q?.rejected_eur ?? 0) },
  ];
  return (
    <svg viewBox="0 0 100 100" className="h-28 w-28 -rotate-90">
      {rings.map((ring) => {
        const c = 2 * Math.PI * ring.r;
        return (
          <g key={ring.r}>
            <circle cx="50" cy="50" r={ring.r} fill="none" stroke="currentColor" strokeWidth="7" className="text-primary/10" />
            <circle
              cx="50"
              cy="50"
              r={ring.r}
              fill="none"
              stroke={ring.color}
              strokeWidth="7"
              strokeLinecap="round"
              strokeDasharray={`${ring.f * c} ${c}`}
            />
          </g>
        );
      })}
    </svg>
  );
}

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
  const w = [100, 80, 62, 46, 32, 22];
  return (
    <div className="my-4 mb-5 flex items-stretch gap-4">
      <div className="flex w-[46%] shrink-0 flex-col">
        {funnel.map((s, i) => {
          const top = w[i] ?? 30;
          const bot = w[i + 1] ?? 22;
          return (
            <div
              key={s.stage}
              className="h-10"
              style={{
                clipPath: `polygon(${(100 - top) / 2}% 0, ${(100 + top) / 2}% 0, ${(100 + bot) / 2}% 100%, ${(100 - bot) / 2}% 100%)`,
                background: `linear-gradient(135deg, hsl(262 83% ${66 - i * 6}%), hsl(290 80% ${68 - i * 6}%))`,
              }}
            />
          );
        })}
      </div>
      <div className="flex flex-1 flex-col">
        {funnel.map((s) => (
          <div key={s.stage} className="flex h-10 items-center justify-between gap-2 text-xs">
            <span className="truncate font-medium">{tStages(s.stage)}</span>
            <span className="shrink-0 font-semibold tabular-nums">{s.count}</span>
            <span className="w-16 shrink-0 text-right text-[11px] text-muted-foreground tabular-nums">
              {eur.format(s.value_eur)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
