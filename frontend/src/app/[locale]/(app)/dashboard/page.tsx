"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartTooltip } from "@/components/charts/tooltip";
import { CHART_COLORS, STAGE_COLORS } from "@/components/charts/palette";
import { api, type DashboardStats, type Lead } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function DashboardPage() {
  const t = useTranslations("dashboard");
  const tLeads = useTranslations("leads.stages");
  const locale = useLocale();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.stats(token).then(setStats).catch(() => setStats(null));
    api.listAllLeads(token).then(setLeads).catch(() => setLeads([]));
  }, []);

  const moneyFmt = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  });
  const intFmt = new Intl.NumberFormat(locale);

  // Sparkline data: leads created per day in the last 14 days
  const sparkData = useMemo(() => {
    const today = new Date();
    const days: { label: string; count: number }[] = [];
    for (let i = 13; i >= 0; i--) {
      const day = new Date(today);
      day.setDate(today.getDate() - i);
      const key = day.toISOString().slice(0, 10);
      const count = leads.filter((l) => l.created_at.slice(0, 10) === key).length;
      days.push({ label: `${day.getDate()}/${day.getMonth() + 1}`, count });
    }
    return days;
  }, [leads]);

  // Stage bar chart
  const stageData = useMemo(() => {
    const byStage = stats?.leads_by_stage ?? {};
    return Object.entries(byStage).map(([stage, count]) => ({
      stage,
      label: tLeads(stage),
      count: Number(count),
      color: STAGE_COLORS[stage] ?? CHART_COLORS.blue,
    }));
  }, [stats, tLeads]);

  const cards: { label: string; value: string | number; accent: string }[] = [
    {
      label: t("totalLeads"),
      value: stats ? intFmt.format(stats.total_leads) : 0,
      accent: "from-indigo-500/15 to-indigo-500/0",
    },
    {
      label: t("totalCustomers"),
      value: stats ? intFmt.format(stats.total_customers) : 0,
      accent: "from-cyan-500/15 to-cyan-500/0",
    },
    {
      label: t("totalDeals"),
      value: stats ? intFmt.format(stats.total_deals) : 0,
      accent: "from-violet-500/15 to-violet-500/0",
    },
    {
      label: t("pipelineValue"),
      value: stats ? moneyFmt.format(stats.pipeline_value_eur || 0) : "—",
      accent: "from-emerald-500/15 to-emerald-500/0",
    },
    {
      label: t("openTasks"),
      value: stats ? intFmt.format(stats.open_tasks) : 0,
      accent: "from-amber-500/15 to-amber-500/0",
    },
    {
      label: t("conversionRate"),
      value: stats ? `${(stats.conversion_rate * 100).toFixed(1)}%` : "—",
      accent: "from-rose-500/15 to-rose-500/0",
    },
    {
      label: t("wonDeals"),
      value: stats ? intFmt.format(stats.won_count) : 0,
      accent: "from-emerald-500/15 to-emerald-500/0",
    },
    {
      label: t("avgAiScore"),
      value: stats?.avg_ai_score != null ? stats.avg_ai_score.toFixed(1) : "—",
      accent: "from-blue-500/15 to-blue-500/0",
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("welcome")}</h1>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
                <div className="text-2xl font-semibold">{value}</div>
              </CardContent>
            </div>
          </Card>
        ))}
      </div>

      {/* Two-up: trend sparkline + stage bars */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("trend14Days")}
            </CardTitle>
          </CardHeader>
          <CardContent className="h-44">
            {leads.length === 0 ? (
              <p className="grid h-full place-items-center text-xs text-muted-foreground">
                {t("noData")}
              </p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={sparkData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                  <defs>
                    <linearGradient id="dashLeadsGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={CHART_COLORS.blue} stopOpacity={0.6} />
                      <stop offset="100%" stopColor={CHART_COLORS.blue} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" interval={2} />
                  <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" allowDecimals={false} width={28} />
                  <Tooltip content={<ChartTooltip valueFormatter={(n) => intFmt.format(n)} />} />
                  <Area
                    type="monotone"
                    dataKey="count"
                    name={t("leadsCreated")}
                    stroke={CHART_COLORS.blue}
                    strokeWidth={2}
                    fill="url(#dashLeadsGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("leadsByStage")}
            </CardTitle>
          </CardHeader>
          <CardContent className="h-44">
            {stageData.every((d) => d.count === 0) ? (
              <p className="grid h-full place-items-center text-xs text-muted-foreground">
                {t("noData")}
              </p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stageData} margin={{ top: 8, right: 8, left: -24, bottom: 0 }}>
                  <XAxis dataKey="label" tick={false} stroke="hsl(var(--muted-foreground))" axisLine={false} />
                  <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" allowDecimals={false} width={24} />
                  <Tooltip content={<ChartTooltip valueFormatter={(n) => intFmt.format(n)} />} />
                  <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                    {stageData.map((d, i) => (
                      <Cell key={i} fill={d.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
