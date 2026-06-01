"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { ArrowRight, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { AuthShell } from "@/components/marketing/auth-shell";
import { api, isMfaChallenge } from "@/lib/api";
import { setToken } from "@/lib/auth";

export default function LoginPage() {
  const tAuth = useTranslations("auth");
  const tMarketing = useTranslations("marketing");
  const locale = useLocale();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // MFA second-step state. When `mfaToken` is set we hide the
  // email/password form and render the code prompt instead. The
  // backend short-lived JWT (5 min) authorises a single call to
  // /mfa/verify; on success we land in the dashboard like a normal
  // login.
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.login(email, password);
      if (isMfaChallenge(res)) {
        setMfaToken(res.mfa_token);
        setMfaCode("");
        return;
      }
      setToken(res.token.access_token);
      router.push(`/${res.user.locale || locale}/dashboard`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  async function submitMfa(e: React.FormEvent) {
    e.preventDefault();
    if (!mfaToken) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.mfaVerify(mfaToken, mfaCode.trim());
      setToken(res.token.access_token);
      router.push(`/${res.user.locale || locale}/dashboard`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Verification failed");
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
              {tMarketing("loginHeroTitle")}
            </h1>
            <p className="mt-5 max-w-md text-base text-muted-foreground sm:text-lg">
              {tMarketing("loginHeroSubtitle")}
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
        {mfaToken ? (
          <>
            <div className="space-y-1">
              <h2 className="text-2xl font-semibold tracking-tight">
                {tAuth("mfaPromptTitle")}
              </h2>
              <p className="text-sm text-muted-foreground">
                {tAuth("mfaPromptSubtitle")}
              </p>
            </div>
            <form onSubmit={submitMfa} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="mfa_code">{tAuth("mfaCodeLabel")}</Label>
                <Input
                  id="mfa_code"
                  // `one-time-code` is the spec value that triggers
                  // SMS / authenticator app autofill on iOS / Android.
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  pattern="[0-9a-fA-F\-]*"
                  autoFocus
                  required
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  placeholder="123456 or backup-code"
                />
                <p className="text-xs text-muted-foreground">
                  {tAuth("mfaCodeHint")}
                </p>
              </div>
              {error && (
                <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {error}
                </div>
              )}
              <Button type="submit" className="w-full" disabled={busy} size="lg">
                {busy ? tAuth("mfaVerifying") : tAuth("mfaVerify")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="w-full"
                onClick={() => {
                  setMfaToken(null);
                  setError(null);
                  setPassword("");
                }}
              >
                {tAuth("mfaCancel")}
              </Button>
            </form>
          </>
        ) : (
          <>
            <div className="space-y-1">
              <h2 className="text-2xl font-semibold tracking-tight">{tAuth("welcomeBack")}</h2>
              <p className="text-sm text-muted-foreground">{tAuth("loginSubtitle")}</p>
            </div>

            <form onSubmit={submit} className="space-y-4">
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
                <div className="flex items-center justify-between">
                  <Label htmlFor="password">{tAuth("password")}</Label>
                  <Link
                    href={`/${locale}/forgot-password`}
                    className="text-xs text-muted-foreground transition-colors hover:text-foreground hover:underline"
                  >
                    {tAuth("forgotPassword")}
                  </Link>
                </div>
                <PasswordInput
                  id="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  visibilityLabels={{
                    show: tAuth("showPassword"),
                    hide: tAuth("hidePassword"),
                  }}
                />
              </div>

              {error && (
                <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {error}
                </div>
              )}

              <Button type="submit" className="group w-full" disabled={busy} size="lg">
                {busy ? tAuth("signingIn") : tAuth("login")}
                {!busy && <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />}
              </Button>
            </form>

            <div className="space-y-3 text-center text-sm">
              <p className="text-muted-foreground">
                {tAuth("needAccount")}{" "}
                <Link href={`/${locale}/register`} className="font-medium text-primary hover:underline">
                  {tAuth("register")}
                </Link>
              </p>
              <p className="text-muted-foreground">
                <Link href={`/${locale}/pricing`} className="hover:text-foreground">
                  {tMarketing("seePricing")} →
                </Link>
              </p>
            </div>
          </>
        )}
      </div>
    </AuthShell>
  );
}
