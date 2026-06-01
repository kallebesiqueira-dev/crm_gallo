"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { ArrowRight, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { AuthShell } from "@/components/marketing/auth-shell";
import { api, type PlanId } from "@/lib/api";
import { setToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

const PLAN_OPTIONS: PlanId[] = ["free", "standard", "premium"];

export default function RegisterPage() {
  const tAuth = useTranslations("auth");
  const tMarketing = useTranslations("marketing");
  const tPricing = useTranslations("pricing");
  const locale = useLocale();
  const router = useRouter();
  const search = useSearchParams();
  const initialPlan = (search.get("plan") as PlanId) || "free";

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [selectedPlan, setSelectedPlan] = useState<PlanId>(initialPlan);
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (PLAN_OPTIONS.includes(initialPlan)) setSelectedPlan(initialPlan);
  }, [initialPlan]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!accepted) {
      setError(tAuth("mustAcceptTerms"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api.register({ email, password, full_name: fullName, locale });
      setToken(res.token.access_token);
      if (selectedPlan !== "free") {
        router.push(`/${res.user.locale || locale}/billing?upgrade=${selectedPlan}`);
      } else {
        router.push(`/${res.user.locale || locale}/dashboard`);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Registration failed";
      if (msg.includes("402") || msg.toLowerCase().includes("seat")) {
        setError(tAuth("seatLimitReached"));
      } else {
        setError(msg);
      }
    } finally {
      setBusy(false);
    }
  }

  const benefits = [
    tMarketing("benefitFreeTier"),
    tMarketing("benefitNoCard"),
    tMarketing("benefitCancel"),
  ];

  return (
    <AuthShell
      brand={
        <div className="space-y-8">
          <div>
            <h1 className="bg-gradient-to-br from-foreground via-foreground to-foreground/60 bg-clip-text text-4xl font-semibold leading-tight tracking-tight text-transparent sm:text-5xl">
              {tMarketing("registerHeroTitle")}
            </h1>
            <p className="mt-5 max-w-md text-base text-muted-foreground sm:text-lg">
              {tMarketing("heroSubheadline")}
            </p>
          </div>
          <ul className="space-y-3">
            {benefits.map((b) => (
              <li key={b} className="flex items-start gap-3 text-sm">
                <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-emerald-500/15 text-emerald-500">
                  <Check className="h-3 w-3" />
                </span>
                <span>{b}</span>
              </li>
            ))}
          </ul>
        </div>
      }
    >
      <div className="space-y-6">
        <div className="space-y-1">
          <h2 className="text-2xl font-semibold tracking-tight">{tAuth("createAccount")}</h2>
          <p className="text-sm text-muted-foreground">{tAuth("registerSubtitle")}</p>
        </div>

        {/* Plan picker */}
        <div className="space-y-2">
          <Label>{tAuth("chooseStartingPlan")}</Label>
          <div className="grid grid-cols-3 gap-2">
            {PLAN_OPTIONS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setSelectedPlan(p)}
                className={cn(
                  "rounded-lg border px-3 py-2 text-left transition-all",
                  selectedPlan === p
                    ? "border-primary bg-primary/5 ring-2 ring-primary/20"
                    : "border-input hover:border-primary/40",
                )}
              >
                <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {tPricing(`plans.${p}.name`)}
                </div>
                <div className="mt-0.5 text-sm font-semibold">
                  {p === "free" ? tPricing("free") : tPricing(`plans.${p}.shortPrice`)}
                </div>
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="full_name">{tAuth("fullName")}</Label>
            <Input
              id="full_name"
              autoComplete="name"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder={tAuth("fullNamePlaceholder")}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">{tAuth("email")}</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">{tAuth("password")}</Label>
            <PasswordInput
              id="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              showStrength
              strengthLabels={{
                weak: tAuth("strengthWeak"),
                fair: tAuth("strengthFair"),
                good: tAuth("strengthGood"),
                strong: tAuth("strengthStrong"),
              }}
              visibilityLabels={{
                show: tAuth("showPassword"),
                hide: tAuth("hidePassword"),
              }}
            />
          </div>

          <label className="flex items-start gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-input"
            />
            <span>{tAuth("acceptTerms")}</span>
          </label>

          {error && (
            <div className="space-y-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              <div>{error}</div>
              {error.toLowerCase().includes(tAuth("seatLimitReached").toLowerCase().slice(0, 10)) && (
                <Link
                  href={`/${locale}/pricing`}
                  className="inline-flex items-center gap-1 font-medium underline"
                >
                  {tMarketing("seePricing")} <ArrowRight className="h-3 w-3" />
                </Link>
              )}
            </div>
          )}

          <Button type="submit" className="group w-full" disabled={busy} size="lg">
            {busy ? tAuth("creatingAccount") : tAuth("createAccount")}
            {!busy && <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />}
          </Button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          {tAuth("haveAccount")}{" "}
          <Link href={`/${locale}/login`} className="font-medium text-primary hover:underline">
            {tAuth("login")}
          </Link>
        </p>
      </div>
    </AuthShell>
  );
}
