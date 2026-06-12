"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import { FileText, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DashboardStats } from "@/lib/api";

/**
 * Financial block (Panoramica finanziaria + Preventivi) — formerly the
 * dashboard's middle row, moved into the Reports tab (skills.md §4: the
 * dashboard slims down to KPIs + action widgets; analytics charts live
 * under Reports). Pure presentational: callers own the stats fetch.
 */
export function FinancialOverview({ stats }: { stats: DashboardStats | null }) {
  const t = useTranslations("dashboard");
  const locale = useLocale();

  const eur2 = useMemo(
    () => new Intl.NumberFormat(locale, { style: "currency", currency: "EUR", minimumFractionDigits: 2 }),
    [locale],
  );

  const q = stats?.quotes;
  const openTotal = (q?.open_eur ?? 0) + (q?.overdue_eur ?? 0);
  const openPct = openTotal > 0 ? Math.round(((q?.open_eur ?? 0) / openTotal) * 100) : 0;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Panel className="p-5 lg:col-span-2">
        <SectionTitle icon={TrendingUp}>{t("financialOverview")}</SectionTitle>
        <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-[1.5fr_1fr]">
          <div>
            <div className="text-xs text-muted-foreground">{t("payments")}</div>
            <div className="text-sm font-semibold">
              {t("total")} {eur2.format(stats?.revenue_total_eur ?? 0)}
            </div>
            <PaymentsBars data={stats?.monthly_revenue ?? []} locale={locale} empty={t("noData")} />
          </div>
          <div className="md:border-l md:border-border md:pl-5">
            <div className="text-xs text-muted-foreground">{t("openAmounts")}</div>
            {openTotal > 0 ? (
              <DonutOpen pct={openPct} />
            ) : (
              <div className="grid h-32 place-items-center text-center text-xs text-muted-foreground">
                {t("noData")}
              </div>
            )}
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
          <div className="min-w-0 flex-1 space-y-2 text-xs">
            <LegendRow color="bg-violet-500" label={t("outstanding")} value={eur2.format(q?.outstanding_eur ?? 0)} />
            <LegendRow color="bg-fuchsia-500" label={t("accepted")} value={eur2.format(q?.accepted_eur ?? 0)} />
            <LegendRow color="bg-rose-400" label={t("rejected")} value={eur2.format(q?.rejected_eur ?? 0)} />
          </div>
        </div>
      </Panel>
    </div>
  );
}

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

function SectionTitle({ icon: Icon, children }: { icon: typeof TrendingUp; children: React.ReactNode }) {
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
      <span className="flex min-w-0 items-center gap-2 text-muted-foreground">
        <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", color)} />
        <span className="truncate">{label}</span>
      </span>
      <span className="shrink-0 whitespace-nowrap font-semibold text-foreground">{value}</span>
    </div>
  );
}

function PaymentsBars({
  data,
  locale,
  empty,
}: {
  data: { month: string; value_eur: number }[];
  locale: string;
  empty: string;
}) {
  const max = Math.max(1, ...data.map((d) => d.value_eur));
  // No closed-won revenue yet → every bar would be an invisible 2% sliver in a
  // big empty box (reads as "broken"). Show a clean empty state at the same
  // height instead.
  const hasData = data.some((d) => d.value_eur > 0);
  if (!hasData) {
    return <div className="mt-3 grid h-36 place-items-center text-xs text-muted-foreground">{empty}</div>;
  }
  const fmt = (m: string) => {
    const d = new Date(`${m}-01T00:00:00`);
    return Number.isNaN(d.getTime()) ? m.slice(5) : d.toLocaleDateString(locale, { month: "short" });
  };
  return (
    <div className="mt-3 flex h-36 items-end gap-1.5">
      {data.map((d) => (
        <div key={d.month} className="flex h-full flex-1 flex-col items-center gap-1">
          {/* The bar's `height: %` needs a parent with a DEFINITE height, or it
              collapses to 0 (the bug that left this chart blank). The column is
              `h-full` and this flex-1 track gives the bar a real height to grow
              against; the bar aligns to the bottom. */}
          <div className="flex w-full flex-1 items-end">
            <div
              className="w-full rounded-t-md bg-gradient-to-t from-violet-600 to-fuchsia-400 transition-all hover:opacity-80"
              style={{ height: `${Math.max(2, (d.value_eur / max) * 100)}%` }}
              title={`${d.month}: ${d.value_eur}`}
            />
          </div>
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
