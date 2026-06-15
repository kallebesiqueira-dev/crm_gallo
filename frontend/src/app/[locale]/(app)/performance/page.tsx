"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { ChartTooltip } from "@/components/charts/tooltip";
import { CHART_COLORS, STAGE_COLORS } from "@/components/charts/palette";
import { useConfirm } from "@/components/confirm-dialog";
import { ReportsView } from "@/components/reports-view";
import { cn } from "@/lib/utils";
import {
  api,
  type GoalMetric,
  type GoalPeriod,
  type PerformanceSummary,
  type SalesGoal,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

const PERIODS: GoalPeriod[] = ["month", "quarter", "year"];

type AnalyticsTab = "performance" | "reports";

function firstOfMonth(): string {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
}

export default function PerformancePage() {
  const t = useTranslations("performance");
  const tCommon = useTranslations("common");
  const tNav = useTranslations("nav");
  const tReports = useTranslations("reports");
  const tStages = useTranslations("leads.stages");
  const locale = useLocale();
  const confirm = useConfirm();

  const [tab, setTab] = useState<AnalyticsTab>("performance");
  const [period, setPeriod] = useState<GoalPeriod>("month");

  // Tab mode: `?tab=reports` (the old /reports deep link) wins, then the last
  // choice from localStorage. Read in an effect — no useSearchParams, so the
  // page needs no Suspense boundary.
  useEffect(() => {
    try {
      const fromUrl = new URLSearchParams(window.location.search).get("tab");
      const stored = localStorage.getItem("analytics-tab");
      const wanted = fromUrl ?? stored;
      if (wanted === "reports" || wanted === "performance") setTab(wanted);
    } catch {
      /* stay on performance */
    }
  }, []);

  function switchTab(next: AnalyticsTab) {
    setTab(next);
    try {
      localStorage.setItem("analytics-tab", next);
      const url = new URL(window.location.href);
      url.searchParams.set("tab", next);
      window.history.replaceState(null, "", url.toString());
    } catch {
      /* non-fatal: tab still switches in-memory */
    }
  }
  const [summary, setSummary] = useState<PerformanceSummary | null>(null);
  const [goals, setGoals] = useState<SalesGoal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Goal create form
  const [gPeriod, setGPeriod] = useState<GoalPeriod>("month");
  const [gMetric, setGMetric] = useState<GoalMetric>("revenue");
  const [gStart, setGStart] = useState(firstOfMonth());
  const [gTarget, setGTarget] = useState("");
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const moneyFmt = useMemo(
    () => new Intl.NumberFormat(locale, { style: "currency", currency: "EUR", maximumFractionDigits: 0 }),
    [locale],
  );
  const intFmt = useMemo(() => new Intl.NumberFormat(locale), [locale]);
  const pctFmt = (n: number) => `${(n * 100).toFixed(1)}%`;

  const loadSummary = useCallback(async (p: GoalPeriod) => {
    const token = getToken();
    if (!token) return;
    setError(null);
    try {
      setSummary(await api.performanceSummary(token, p));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }, []);

  const loadGoals = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      setGoals(await api.listGoals(token));
    } catch {
      /* goals are non-critical; summary still renders */
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([loadSummary(period), loadGoals()]).finally(() => setLoading(false));
  }, [period, loadSummary, loadGoals]);

  async function handleCreateGoal(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    const target = Number(gTarget);
    if (!token || !gStart || !Number.isFinite(target) || target < 0) return;
    setCreating(true);
    setError(null);
    try {
      await api.createGoal(token, {
        period: gPeriod,
        period_start: gStart,
        metric: gMetric,
        target,
      });
      setGTarget("");
      await loadGoals();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setCreating(false);
    }
  }

  async function handleDeleteGoal(goal: SalesGoal) {
    const token = getToken();
    if (!token) return;
    const ok = await confirm({
      title: t("confirmDeleteTitle"),
      description: t("confirmDeleteBody"),
      confirmLabel: tCommon("delete"),
    });
    if (!ok) return;
    setBusyId(goal.id);
    try {
      await api.deleteGoal(token, goal.id);
      await loadGoals();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusyId(null);
    }
  }

  const funnelData = useMemo(
    () =>
      (summary?.lead_funnel ?? []).map((f) => ({
        stage: f.stage,
        label: tStages(f.stage),
        count: f.count,
        color: STAGE_COLORS[f.stage] ?? CHART_COLORS.blue,
      })),
    [summary, tStages],
  );

  const cards = useMemo(() => {
    if (!summary) return [];
    const days = (n: number | null) => (n == null ? "—" : t("daysValue", { days: n }));
    return [
      { label: t("wonValue"), value: moneyFmt.format(summary.won_value_eur), accent: "from-emerald-500/15 to-emerald-500/0" },
      { label: t("wonCount"), value: intFmt.format(summary.won_count), accent: "from-indigo-500/15 to-indigo-500/0" },
      { label: t("winRate"), value: pctFmt(summary.win_rate), accent: "from-violet-500/15 to-violet-500/0" },
      { label: t("lostCount"), value: intFmt.format(summary.lost_count), accent: "from-rose-500/15 to-rose-500/0" },
      { label: t("avgDays"), value: days(summary.avg_days_to_close), accent: "from-cyan-500/15 to-cyan-500/0" },
      { label: t("medianDays"), value: days(summary.median_days_to_close), accent: "from-blue-500/15 to-blue-500/0" },
      { label: t("leadConversion"), value: pctFmt(summary.lead_conversion_rate), accent: "from-amber-500/15 to-amber-500/0" },
      { label: t("leadsLost"), value: intFmt.format(summary.leads_lost), accent: "from-rose-500/15 to-rose-500/0" },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summary, moneyFmt, intFmt, t]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {tab === "reports" ? tReports("title") : t("title")}
          </h1>
          <p className="text-sm text-muted-foreground">
            {tab === "reports" ? tReports("subtitle") : t("subtitle")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Performance | Report — one analytics screen (skills.md §4) */}
          <div className="inline-flex rounded-md border p-0.5" role="tablist">
            {(
              [
                { key: "performance" as const, label: tNav("performance") },
                { key: "reports" as const, label: tNav("reports") },
              ]
            ).map(({ key, label }) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                onClick={() => switchTab(key)}
                className={cn(
                  "rounded px-3 py-1.5 text-sm font-medium transition-colors",
                  tab === key
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          {tab === "performance" && (
            <div className="flex rounded-md border bg-card p-0.5">
              {PERIODS.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPeriod(p)}
                  className={
                    "rounded px-3 py-1 text-sm font-medium transition-colors " +
                    (period === p
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:text-foreground")
                  }
                >
                  {t(`period.${p}`)}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {tab === "reports" ? (
        <ReportsView />
      ) : (
        <>
      {/* KPI tiles */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map(({ label, value, accent }) => (
          <Card key={label} className="relative overflow-hidden">
            <div aria-hidden className={`pointer-events-none absolute inset-0 bg-gradient-to-br ${accent}`} />
            <div className="relative">
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {label}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-semibold">{loading ? "—" : value}</div>
              </CardContent>
            </div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Leaderboard */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">{t("leaderboard")}</CardTitle>
          </CardHeader>
          <CardContent>
            {!summary || summary.leaderboard.length === 0 ? (
              <p className="py-8 text-center text-xs text-muted-foreground">{t("noData")}</p>
            ) : (
              <ul className="space-y-2">
                {summary.leaderboard.map((row, i) => (
                  <li key={row.owner_id ?? `none-${i}`} className="flex items-center justify-between gap-3 text-sm">
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-muted text-xs font-semibold">
                        {i + 1}
                      </span>
                      <span className="truncate">{row.owner_name}</span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <span className="font-medium">{moneyFmt.format(row.won_value_eur)}</span>
                      <Badge variant="secondary">{t("dealsWon", { count: row.won_count })}</Badge>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Lead funnel */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">{t("funnel")}</CardTitle>
          </CardHeader>
          <CardContent className="h-56">
            {funnelData.every((d) => d.count === 0) ? (
              <p className="grid h-full place-items-center text-xs text-muted-foreground">{t("noData")}</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={funnelData} margin={{ top: 8, right: 8, left: -24, bottom: 0 }}>
                  <XAxis dataKey="label" tick={{ fontSize: 9 }} stroke="hsl(var(--muted-foreground))" interval={0} />
                  <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" allowDecimals={false} width={24} />
                  <Tooltip content={<ChartTooltip valueFormatter={(n) => intFmt.format(n)} />} />
                  <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                    {funnelData.map((d, i) => (
                      <Cell key={i} fill={d.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Goals */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">{t("goals")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={handleCreateGoal} className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5 lg:items-end">
            <div className="space-y-1">
              <Label htmlFor="g-metric">{t("metric")}</Label>
              <Select
                id="g-metric"
                value={gMetric}
                onChange={(e) => setGMetric(e.target.value as GoalMetric)}
              >
                <option value="revenue">{t("metricRevenue")}</option>
                <option value="deal_count">{t("metricDealCount")}</option>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="g-period">{t("goalPeriod")}</Label>
              <Select
                id="g-period"
                value={gPeriod}
                onChange={(e) => setGPeriod(e.target.value as GoalPeriod)}
              >
                {PERIODS.map((p) => (
                  <option key={p} value={p}>
                    {t(`period.${p}`)}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="g-start">{t("periodStart")}</Label>
              <Input id="g-start" type="date" value={gStart} onChange={(e) => setGStart(e.target.value)} required />
            </div>
            <div className="space-y-1">
              <Label htmlFor="g-target">{t("target")}</Label>
              <Input
                id="g-target"
                type="number"
                min="0"
                step="any"
                value={gTarget}
                onChange={(e) => setGTarget(e.target.value)}
                placeholder={gMetric === "revenue" ? "10000" : "20"}
                required
              />
            </div>
            <Button type="submit" disabled={creating || !gTarget}>
              {t("addGoal")}
            </Button>
          </form>

          {goals.length === 0 ? (
            <p className="py-4 text-center text-xs text-muted-foreground">{t("noGoals")}</p>
          ) : (
            <ul className="space-y-3">
              {goals.map((goal) => {
                const pct = Math.min(goal.attainment_pct, 1);
                const reached = goal.attainment_pct >= 1;
                const fmt = goal.metric === "revenue" ? moneyFmt.format : (n: number) => intFmt.format(n);
                return (
                  <li key={goal.id} className="rounded-md border p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-sm">
                        <Badge variant="secondary">
                          {goal.metric === "revenue" ? t("metricRevenue") : t("metricDealCount")}
                        </Badge>
                        <span className="text-muted-foreground">
                          {t(`period.${goal.period}`)} · {goal.period_start}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-sm">
                        <span className="font-medium">
                          {fmt(goal.attainment)} / {fmt(goal.target)}
                        </span>
                        <Badge variant={reached ? "success" : "secondary"}>{pctFmt(goal.attainment_pct)}</Badge>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeleteGoal(goal)}
                          disabled={busyId === goal.id}
                          aria-label={tCommon("delete")}
                        >
                          {tCommon("delete")}
                        </Button>
                      </div>
                    </div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
                      <div
                        className={"h-full rounded-full " + (reached ? "bg-emerald-500" : "bg-primary")}
                        style={{ width: `${pct * 100}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>
        </>
      )}
    </div>
  );
}
