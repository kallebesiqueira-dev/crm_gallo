"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import {
  ArrowRight,
  CheckCircle2,
  CreditCard,
  ExternalLink,
  Gauge,
  Receipt,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { SearchParamWatcher } from "@/components/search-param-watcher";
import { api, type BillingMe, type PlanOut, type PlanId, type BillingCycle } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

const PLAN_ACCENT: Record<PlanId, string> = {
  free: "from-slate-500/20 via-slate-500/5 to-transparent",
  standard: "from-primary/30 via-primary/10 to-transparent",
  business: "from-violet-500/30 via-blue-500/10 to-transparent",
  premium: "from-amber-500/30 via-fuchsia-500/15 to-transparent",
};

const PLAN_BADGE: Record<PlanId, string> = {
  free: "bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20",
  standard: "bg-primary/10 text-primary border-primary/20",
  business: "bg-violet-500/10 text-violet-700 dark:text-violet-300 border-violet-500/20",
  premium:
    "bg-gradient-to-r from-amber-500/15 to-fuchsia-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30",
};

export default function BillingPage() {
  const t = useTranslations("billing");
  const tPricing = useTranslations("pricing");
  const locale = useLocale();

  const [me, setMe] = useState<BillingMe | null>(null);
  const [plans, setPlans] = useState<PlanOut[] | null>(null);
  const [busy, setBusy] = useState<PlanId | "portal" | null>(null);
  const [cycle, setCycle] = useState<BillingCycle>("monthly");
  const [banner, setBanner] = useState<{ kind: "ok" | "warn"; text: string } | null>(null);
  const [stripeFlag, setStripeFlag] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.billingMe(token).then(setMe).catch(() => setMe(null));
    api.plans().then(setPlans).catch(() => setPlans([]));
  }, []);

  // Checkout round-trips back here with ?stripe=success|cancel. The flag is
  // read by <SearchParamWatcher> so useSearchParams() stays inside its own
  // Suspense boundary (required for static prerender in Next 15).
  useEffect(() => {
    if (stripeFlag === "success") {
      setBanner({ kind: "ok", text: t("checkoutSuccess") });
    } else if (stripeFlag === "cancel") {
      setBanner({ kind: "warn", text: t("checkoutCanceled") });
    }
  }, [stripeFlag, t]);

  const moneyFmt = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  });

  async function startUpgrade(planId: PlanId) {
    const token = getToken();
    if (!token) return;
    setBusy(planId);
    setBanner(null);
    try {
      const { url } = await api.checkout(token, planId, cycle);
      window.location.assign(url);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Checkout failed";
      setBanner({
        kind: "warn",
        text: msg.includes("503") || msg.toLowerCase().includes("not configured")
          ? t("stripeNotConfigured")
          : msg,
      });
      setBusy(null);
    }
  }

  async function openPortal() {
    const token = getToken();
    if (!token) return;
    setBusy("portal");
    try {
      const { url } = await api.portal(token);
      window.location.assign(url);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Portal failed";
      setBanner({
        kind: "warn",
        text: msg.includes("503") ? t("stripeNotConfigured") : msg,
      });
      setBusy(null);
    }
  }

  if (!me) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const currentPlanDescriptor = plans?.find((p) => p.id === me.plan);
  const seatPct =
    me.seat_limit && me.seat_limit > 0 ? Math.min(100, (me.seats_used / me.seat_limit) * 100) : null;
  const onFree = me.plan === "free";
  const trialActive = me.trial_ends_at && new Date(me.trial_ends_at) > new Date();
  const startedFmt = me.plan_started_at
    ? new Date(me.plan_started_at).toLocaleDateString(locale, {
        day: "numeric",
        month: "long",
        year: "numeric",
      })
    : "—";
  const renewedFmt = me.plan_renewed_at
    ? new Date(me.plan_renewed_at).toLocaleDateString(locale, {
        day: "numeric",
        month: "long",
        year: "numeric",
      })
    : "—";

  return (
    <div className="space-y-8">
      <Suspense fallback={null}>
        <SearchParamWatcher name="stripe" onValue={setStripeFlag} />
      </Suspense>
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        <Button asChild variant="ghost" size="sm">
          <Link href={`/${locale}/pricing`}>
            {t("comparePlans")} <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
      </div>

      {banner && (
        <div
          className={cn(
            "flex items-center gap-2 rounded-lg border px-4 py-3 text-sm",
            banner.kind === "ok"
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-900 dark:text-emerald-200"
              : "border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-200",
          )}
        >
          {banner.kind === "ok" ? <CheckCircle2 className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
          {banner.text}
        </div>
      )}

      {/* Current plan card */}
      <Card className="relative overflow-hidden">
        <div
          aria-hidden
          className={cn(
            "pointer-events-none absolute inset-0 bg-gradient-to-br",
            PLAN_ACCENT[me.plan],
          )}
        />
        <CardHeader className="relative">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {t("currentPlan")}
              </div>
              <div className="mt-1 flex items-center gap-3">
                <span className="text-3xl font-semibold tracking-tight">
                  {currentPlanDescriptor?.name ?? me.plan}
                </span>
                <span
                  className={cn(
                    "rounded-full border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                    PLAN_BADGE[me.plan],
                  )}
                >
                  {me.billing_cycle}
                </span>
                {trialActive && (
                  <span className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
                    {t("trial")}
                  </span>
                )}
              </div>
              {currentPlanDescriptor && (
                <p className="mt-1 text-sm text-muted-foreground">
                  {currentPlanDescriptor.tagline}
                </p>
              )}
            </div>
            <div className="flex flex-col items-end gap-2">
              {!onFree && me.stripe_configured && (
                <Button onClick={openPortal} disabled={busy === "portal"} variant="outline" size="sm">
                  <CreditCard className="h-4 w-4" />
                  {busy === "portal" ? t("opening") : t("manageBilling")}
                  <ExternalLink className="h-3 w-3" />
                </Button>
              )}
              {onFree && (
                <Button onClick={() => startUpgrade("standard")} disabled={busy !== null}>
                  <TrendingUp className="h-4 w-4" />
                  {t("upgrade")}
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="relative">
          <div className="grid gap-4 sm:grid-cols-3">
            <MetricTile
              icon={<Users className="h-4 w-4" />}
              label={t("seatsUsed")}
              value={
                me.seat_limit
                  ? `${me.seats_used} / ${me.seat_limit}`
                  : `${me.seats_used} · ${t("unlimited")}`
              }
              progressPct={seatPct ?? undefined}
            />
            <MetricTile
              icon={<Gauge className="h-4 w-4" />}
              label={t("startedOn")}
              value={startedFmt}
            />
            <MetricTile
              icon={<Receipt className="h-4 w-4" />}
              label={onFree ? t("nextSteps") : t("renewedOn")}
              value={onFree ? t("nothingToBill") : renewedFmt}
            />
          </div>

          {onFree && (
            <div className="mt-6 rounded-lg border border-dashed bg-background/60 p-4">
              <div className="flex items-start gap-3">
                <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                  <Sparkles className="h-4 w-4" />
                </div>
                <div>
                  <div className="text-sm font-medium">{t("freeBannerTitle")}</div>
                  <p className="mt-1 text-sm text-muted-foreground">{t("freeBannerBody")}</p>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Upgrade matrix */}
      {onFree && plans && plans.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>{t("availablePlans")}</CardTitle>
              <CycleToggle cycle={cycle} onChange={setCycle} t={tPricing} />
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-3">
              {plans.map((plan) => (
                <UpgradeCard
                  key={plan.id}
                  plan={plan}
                  cycle={cycle}
                  moneyFmt={moneyFmt}
                  current={plan.id === me.plan}
                  busy={busy === plan.id}
                  onChoose={() => (plan.id === "free" ? undefined : startUpgrade(plan.id))}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Invoice / activity placeholder — Stripe Portal handles real invoices */}
      <Card>
        <CardHeader>
          <CardTitle>{t("billingHistory")}</CardTitle>
        </CardHeader>
        <CardContent>
          {onFree ? (
            <p className="text-sm text-muted-foreground">{t("noInvoicesYet")}</p>
          ) : me.stripe_configured ? (
            <div className="rounded-lg border border-dashed p-6 text-center">
              <Receipt className="mx-auto h-6 w-6 text-muted-foreground" />
              <p className="mt-2 text-sm text-muted-foreground">{t("invoicesAtPortal")}</p>
              <Button onClick={openPortal} variant="outline" size="sm" className="mt-4">
                <ExternalLink className="h-3 w-3" />
                {t("openPortal")}
              </Button>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t("stripeNotConfigured")}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function MetricTile({
  icon,
  label,
  value,
  progressPct,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  progressPct?: number;
}) {
  return (
    <div className="rounded-lg border bg-background/70 p-4">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-2 text-lg font-semibold">{value}</div>
      {typeof progressPct === "number" && (
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full rounded-full transition-all",
              progressPct >= 90 ? "bg-red-500" : progressPct >= 70 ? "bg-amber-500" : "bg-primary",
            )}
            style={{ width: `${progressPct}%` }}
          />
        </div>
      )}
    </div>
  );
}

function CycleToggle({
  cycle,
  onChange,
  t,
}: {
  cycle: BillingCycle;
  onChange: (c: BillingCycle) => void;
  t: (k: string) => string;
}) {
  return (
    <div className="inline-flex items-center rounded-full border bg-muted/40 p-1 text-xs">
      <button
        type="button"
        onClick={() => onChange("monthly")}
        className={cn(
          "rounded-full px-3 py-1 font-medium transition-all",
          cycle === "monthly" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground",
        )}
      >
        {t("monthly")}
      </button>
      <button
        type="button"
        onClick={() => onChange("yearly")}
        className={cn(
          "rounded-full px-3 py-1 font-medium transition-all",
          cycle === "yearly" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground",
        )}
      >
        {t("yearly")} <span className="text-emerald-600 dark:text-emerald-300">-20%</span>
      </button>
    </div>
  );
}

function UpgradeCard({
  plan,
  cycle,
  moneyFmt,
  current,
  busy,
  onChoose,
}: {
  plan: PlanOut;
  cycle: BillingCycle;
  moneyFmt: Intl.NumberFormat;
  current: boolean;
  busy: boolean;
  onChoose: () => void;
}) {
  const t = useTranslations("pricing");
  const isFree = plan.id === "free";
  const price = cycle === "yearly" ? plan.yearly_eur_per_user : plan.monthly_eur;

  return (
    <div
      className={cn(
        "relative flex flex-col rounded-xl border p-5 transition-colors",
        plan.highlighted && !current && "border-primary/40 ring-1 ring-primary/20",
        current && "border-emerald-500/40 bg-emerald-500/5",
      )}
    >
      {current && (
        <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="h-3 w-3" /> {t("currentPlan")}
        </span>
      )}
      <div className="text-sm font-semibold">{plan.name}</div>
      <p className="mt-1 text-xs text-muted-foreground">{plan.tagline}</p>
      <div className="mt-4 flex items-baseline gap-1">
        <span className="text-2xl font-semibold">
          {isFree ? t("free") : moneyFmt.format(price)}
        </span>
        {!isFree && <span className="text-xs text-muted-foreground">{t("perUserPerMonth")}</span>}
      </div>
      <Button
        type="button"
        onClick={onChoose}
        disabled={busy || current || isFree}
        className="mt-4"
        variant={plan.highlighted ? "default" : "outline"}
        size="sm"
      >
        {current ? t("currentPlan") : busy ? t("redirecting") : isFree ? t("startFree") : t("choose")}
      </Button>
    </div>
  );
}
