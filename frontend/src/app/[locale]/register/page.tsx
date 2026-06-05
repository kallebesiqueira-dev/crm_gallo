"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { ArrowRight, Check, MailCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { AuthShell } from "@/components/marketing/auth-shell";
import { SearchParamWatcher } from "@/components/search-param-watcher";
import { api, type PlanId } from "@/lib/api";
import { setToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

const PLAN_OPTIONS: PlanId[] = ["free", "standard", "business", "premium"];

export default function RegisterPage() {
  const tAuth = useTranslations("auth");
  const tMarketing = useTranslations("marketing");
  const tPricing = useTranslations("pricing");
  const locale = useLocale();
  const router = useRouter();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [selectedPlan, setSelectedPlan] = useState<PlanId>("free");
  const [planParam, setPlanParam] = useState<string | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // When the backend requires email confirmation we swap the form for a
  // "check your inbox" screen instead of logging the user in.
  const [verificationSent, setVerificationSent] = useState(false);
  const [resendBusy, setResendBusy] = useState(false);
  const [resendDone, setResendDone] = useState(false);

  // The starting plan can be deep-linked via ?plan=… (set by the pricing
  // cards). `planParam` is fed by <SearchParamWatcher> so useSearchParams()
  // stays inside its own Suspense boundary.
  useEffect(() => {
    const plan = (planParam as PlanId) || "free";
    if (PLAN_OPTIONS.includes(plan)) setSelectedPlan(plan);
  }, [planParam]);

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
      // Common path: self-signup must confirm their email first. No token
      // is issued — show the "check your inbox" screen instead of logging
      // in. (The first user / install founder is auto-verified and comes
      // back with a token, falling through to the login+redirect below.)
      if (res.verification_required || !res.token) {
        setVerificationSent(true);
        return;
      }
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

  async function resendVerification() {
    setResendBusy(true);
    try {
      await api.verifyEmailResend(email);
    } catch {
      // Resend is best-effort and the backend always 204s for a valid
      // request shape — never block the UI on it.
    } finally {
      setResendDone(true);
      setResendBusy(false);
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
        <div className="flex flex-col items-center gap-7 text-center lg:px-6">
          <div className="relative">
            <div
              aria-hidden
              className="pointer-events-none absolute -inset-6 -z-10 rounded-full bg-violet-600/25 blur-3xl"
            />
            <Image
              src="/gallo-login.png"
              alt="GALLO CRM"
              width={245}
              height={439}
              priority
              sizes="(min-width: 1024px) 260px, 45vw"
              className="h-auto w-auto max-h-[58vh] select-none drop-shadow-[0_24px_60px_rgba(124,58,237,0.30)]"
            />
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
      <Suspense fallback={null}>
        <SearchParamWatcher name="plan" onValue={setPlanParam} />
      </Suspense>
      {verificationSent ? (
        <div className="space-y-6">
          <div className="grid h-12 w-12 place-items-center rounded-full bg-emerald-500/10 text-emerald-500">
            <MailCheck className="h-6 w-6" />
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold tracking-tight">
              {tAuth("verifySentTitle")}
            </h2>
            <p className="text-sm text-muted-foreground">
              {tAuth("verifySentBody", { email })}
            </p>
          </div>
          <p className="text-xs text-muted-foreground">{tAuth("verifySentNote")}</p>
          {resendDone ? (
            <p className="text-sm text-emerald-600">{tAuth("verifyResendDone")}</p>
          ) : (
            <Button
              type="button"
              variant="outline"
              className="w-full"
              disabled={resendBusy}
              onClick={resendVerification}
            >
              {resendBusy ? tAuth("verifyResendSending") : tAuth("verifyResend")}
            </Button>
          )}
          <p className="text-center text-sm text-muted-foreground">
            <Link href={`/${locale}/login`} className="font-medium text-primary hover:underline">
              {tMarketing("backToLogin")}
            </Link>
          </p>
        </div>
      ) : (
      <div className="space-y-6">
        <div className="space-y-1">
          <h2 className="text-2xl font-semibold tracking-tight">{tAuth("createAccount")}</h2>
          <p className="text-sm text-muted-foreground">{tAuth("registerSubtitle")}</p>
        </div>

        {/* Plan picker */}
        <div className="space-y-2">
          <Label>{tAuth("chooseStartingPlan")}</Label>
          <div className="grid grid-cols-2 gap-2">
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
      )}
    </AuthShell>
  );
}
