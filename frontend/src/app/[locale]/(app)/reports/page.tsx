"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartTooltip } from "@/components/charts/tooltip";
import {
  CHART_COLORS,
  CURRENCY_COLORS,
  STAGE_COLORS,
  rotatingColor,
} from "@/components/charts/palette";
import { api, type DashboardStats, type Deal, type Lead } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function ReportsPage() {
  const t = useTranslations("reports");
  const tStages = useTranslations("leads.stages");
  const locale = useLocale();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    Promise.all([
      api.stats(token).catch(() => null),
      api.listDeals(token).catch(() => []),
      api.listAllLeads(token).catch(() => []),
    ]).then(([s, d, l]) => {
      setStats(s);
      setDeals(d ?? []);
      setLeads(l ?? []);
    });
  }, []);

  const moneyFmt = useMemo(
    () =>
      new Intl.NumberFormat(locale, {
        style: "currency",
        currency: "EUR",
        maximumFractionDigits: 0,
      }),
    [locale],
  );
  const intFmt = useMemo(() => new Intl.NumberFormat(locale), [locale]);

  // Leads by stage (BarChart)
  const stageData = useMemo(() => {
    const byStage = stats?.leads_by_stage ?? {};
    return Object.entries(byStage).map(([stage, count]) => ({
      stage,
      label: tStages(stage),
      count: Number(count),
      color: STAGE_COLORS[stage] ?? CHART_COLORS.blue,
    }));
  }, [stats, tStages]);

  // Leads created per day for the last 30 days (AreaChart)
  const trendData = useMemo(() => {
    const today = new Date();
    const days: { label: string; key: string; count: number }[] = [];
    for (let i = 29; i >= 0; i--) {
      const day = new Date(today);
      day.setDate(today.getDate() - i);
      const key = day.toISOString().slice(0, 10);
      const count = leads.filter((l) => l.created_at.slice(0, 10) === key).length;
      days.push({
        key,
        label: day.toLocaleDateString(locale, { day: "numeric", month: "short" }),
        count,
      });
    }
    return days;
  }, [leads, locale]);

  // Pipeline by currency (PieChart)
  const currencyData = useMemo(() => {
    const totals: Record<string, number> = {};
    const won: Record<string, number> = {};
    deals.forEach((d) => {
      totals[d.currency] = (totals[d.currency] ?? 0) + d.value;
      if (d.stage === "won") won[d.currency] = (won[d.currency] ?? 0) + d.value;
    });
    return Object.entries(totals).map(([currency, value]) => ({
      name: currency,
      value: Math.round(value),
      won: Math.round(won[currency] ?? 0),
      color: CURRENCY_COLORS[currency] ?? CHART_COLORS.blue,
    }));
  }, [deals]);

  // Stage funnel (HorizontalBarChart with conversion)
  const funnelData = useMemo(() => {
    const order = [
      "new",
      "contacted",
      "qualified",
      "proposal_sent",
      "negotiation",
      "won",
    ];
    return order
      .filter((s) => stats?.leads_by_stage[s] !== undefined)
      .map((s, i) => ({
        stage: s,
        label: tStages(s),
        count: Number(stats?.leads_by_stage[s] ?? 0),
        color: rotatingColor(i),
      }));
  }, [stats, tStages]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      {/* Summary tiles */}
      {stats && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label={t("totalLeads")} value={intFmt.format(stats.total_leads)} accent="indigo" />
          <Metric
            label={t("conversionRate")}
            value={`${(stats.conversion_rate * 100).toFixed(1)}%`}
            accent="emerald"
          />
          <Metric label={t("totalDeals")} value={intFmt.format(stats.total_deals)} accent="violet" />
          <Metric label={t("totalCustomers")} value={intFmt.format(stats.total_customers)} accent="amber" />
        </div>
      )}

      {/* Trend area chart */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("leadsLast30Days")}</CardTitle>
        </CardHeader>
        <CardContent>
          {leads.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">{t("noData")}</p>
          ) : (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trendData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="leadsGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={CHART_COLORS.blue} stopOpacity={0.6} />
                      <stop offset="100%" stopColor={CHART_COLORS.blue} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis
                    dataKey="label"
                    tick={{ fontSize: 11 }}
                    stroke="hsl(var(--muted-foreground))"
                    interval={4}
                  />
                  <YAxis
                    tick={{ fontSize: 11 }}
                    stroke="hsl(var(--muted-foreground))"
                    allowDecimals={false}
                  />
                  <Tooltip content={<ChartTooltip valueFormatter={(n) => intFmt.format(n)} />} />
                  <Area
                    type="monotone"
                    dataKey="count"
                    name={t("leadsCreated")}
                    stroke={CHART_COLORS.blue}
                    strokeWidth={2}
                    fill="url(#leadsGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Leads by stage — vertical bars */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("leadsByStage")}</CardTitle>
          </CardHeader>
          <CardContent>
            {stageData.every((d) => d.count === 0) ? (
              <p className="py-12 text-center text-sm text-muted-foreground">{t("noData")}</p>
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stageData}>
                    <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                    <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" allowDecimals={false} />
                    <Tooltip content={<ChartTooltip valueFormatter={(n) => intFmt.format(n)} />} />
                    <Bar dataKey="count" name={t("leads")} radius={[8, 8, 0, 0]}>
                      {stageData.map((d, i) => (
                        <Cell key={i} fill={d.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Pipeline value by currency — donut */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("pipelineValue")}</CardTitle>
          </CardHeader>
          <CardContent>
            {currencyData.length === 0 ? (
              <p className="py-12 text-center text-sm text-muted-foreground">{t("noData")}</p>
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Tooltip
                      content={
                        <ChartTooltip
                          valueFormatter={(n) =>
                            new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(n)
                          }
                        />
                      }
                    />
                    <Pie
                      data={currencyData}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={50}
                      outerRadius={90}
                      paddingAngle={2}
                    >
                      {currencyData.map((d, i) => (
                        <Cell key={i} fill={d.color} />
                      ))}
                    </Pie>
                    <Legend
                      iconType="circle"
                      wrapperStyle={{ fontSize: 12 }}
                      formatter={(value) => <span className="text-muted-foreground">{value}</span>}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Funnel — horizontal bars */}
      {funnelData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("salesFunnel")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart layout="vertical" data={funnelData} margin={{ left: 16 }}>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" allowDecimals={false} />
                  <YAxis
                    type="category"
                    dataKey="label"
                    tick={{ fontSize: 12 }}
                    stroke="hsl(var(--muted-foreground))"
                    width={120}
                  />
                  <Tooltip content={<ChartTooltip valueFormatter={(n) => intFmt.format(n)} />} />
                  <Bar dataKey="count" name={t("leads")} radius={[0, 8, 8, 0]}>
                    {funnelData.map((d, i) => (
                      <Cell key={i} fill={d.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Currency breakdown table */}
      {currencyData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("breakdownByCurrency")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-2">
              {currencyData.map((c) => (
                <div
                  key={c.name}
                  className="flex items-center justify-between rounded-lg border bg-card p-3"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: c.color }}
                    />
                    <span className="text-xs uppercase tracking-wider text-muted-foreground">
                      {c.name}
                    </span>
                  </div>
                  <div className="text-right">
                    <div className="text-base font-semibold">
                      {moneyFmt.format(c.value).replace("€", c.name + " ")}
                    </div>
                    <div className="text-[10px] text-emerald-600">
                      {t("won")}: {c.won.toLocaleString(locale)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number;
  accent: "indigo" | "emerald" | "violet" | "amber";
}) {
  const accentStyle: Record<string, string> = {
    indigo: "from-indigo-500/20 to-indigo-500/0",
    emerald: "from-emerald-500/20 to-emerald-500/0",
    violet: "from-violet-500/20 to-violet-500/0",
    amber: "from-amber-500/20 to-amber-500/0",
  };
  return (
    <div className="relative overflow-hidden rounded-lg border bg-card p-4">
      <div
        aria-hidden
        className={`pointer-events-none absolute inset-0 bg-gradient-to-br ${accentStyle[accent]}`}
      />
      <div className="relative">
        <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
        <div className="mt-1 text-2xl font-semibold">{value}</div>
      </div>
    </div>
  );
}
