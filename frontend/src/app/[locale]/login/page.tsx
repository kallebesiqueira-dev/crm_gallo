"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { useLocale, useTranslations } from "next-intl";
import { ArrowRight, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { AuthShell } from "@/components/marketing/auth-shell";
import { MicrosoftIcon } from "@/components/microsoft-icon";
import { GoogleIcon } from "@/components/google-icon";
import { api, API_URL, ApiError, isMfaChallenge, isMfaSetupRequired } from "@/lib/api";
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
  // Set when login fails with 403 email_not_verified — swaps the generic
  // error for a "verify your email" notice + a resend button.
  const [needsVerification, setNeedsVerification] = useState(false);
  const [resendBusy, setResendBusy] = useState(false);
  const [resendDone, setResendDone] = useState(false);
  // Social login: ask the backend which providers are wired so we only render
  // a button that actually works. `oauthError` surfaces the hint the callback
  // bounces back with (?oauth=no_account / no_email) for an unmatched email.
  const [msEnabled, setMsEnabled] = useState(false);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [oauthError, setOauthError] = useState<string | null>(null);
  useEffect(() => {
    api
      .oauthProviders()
      .then((p) => {
        setMsEnabled(p.microsoft);
        setGoogleEnabled(p.google);
      })
      .catch(() => {});
    const o = new URLSearchParams(window.location.search).get("oauth");
    if (o) setOauthError(o);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNeedsVerification(false);
    setResendDone(false);
    try {
      const res = await api.login(email, password);
      if (isMfaChallenge(res)) {
        setMfaToken(res.mfa_token);
        setMfaCode("");
        return;
      }
      // Privileged user who must enroll before reaching any data. The
      // session cookies are already set, so route straight into the
      // forced-enrollment page rather than the dashboard (which would
      // just 403 every data fetch).
      if (isMfaSetupRequired(res)) {
        setToken(res.token.access_token);
        router.push(`/${res.user.locale || locale}/mfa-setup`);
        return;
      }
      setToken(res.token.access_token);
      router.push(`/${res.user.locale || locale}/dashboard`);
    } catch (e) {
      // 403 with the exact `email_not_verified` detail → the account
      // exists but hasn't confirmed its email. Show the verify + resend
      // UI instead of the generic error.
      if (e instanceof ApiError && e.status === 403 && e.message === "email_not_verified") {
        setNeedsVerification(true);
      } else {
        setError(e instanceof Error ? e.message : "Login failed");
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
      // Resend is best-effort — the backend always 204s for a valid
      // request shape, so never block the UI on it.
    } finally {
      setResendDone(true);
      setResendBusy(false);
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

            {oauthError && (
              <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
                {oauthError === "no_account" ? tAuth("oauthNoAccount") : tAuth("oauthNoEmail")}
              </div>
            )}

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

              {needsVerification && (
                <div className="space-y-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
                  <div>{tAuth("loginNotVerified")}</div>
                  {resendDone ? (
                    <p className="text-emerald-600 dark:text-emerald-400">
                      {tAuth("verifyResendDone")}
                    </p>
                  ) : (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={resendBusy}
                      onClick={resendVerification}
                    >
                      {resendBusy ? tAuth("verifyResendSending") : tAuth("verifyResend")}
                    </Button>
                  )}
                </div>
              )}

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

            {(msEnabled || googleEnabled) && (
              <div className="space-y-4">
                <div className="flex items-center gap-3 text-xs uppercase text-muted-foreground">
                  <span className="h-px flex-1 bg-border" />
                  {tAuth("orContinueWith")}
                  <span className="h-px flex-1 bg-border" />
                </div>
                <div className="space-y-2">
                  {googleEnabled && (
                    <a
                      href={`${API_URL}/api/auth/oauth/google/start`}
                      className="flex w-full items-center justify-center gap-2.5 rounded-md border bg-background px-4 py-2.5 text-sm font-medium shadow-sm transition-colors hover:bg-accent"
                    >
                      <GoogleIcon className="h-[18px] w-[18px]" />
                      {tAuth("continueWithGoogle")}
                    </a>
                  )}
                  {msEnabled && (
                    <a
                      href={`${API_URL}/api/auth/oauth/microsoft/start`}
                      className="flex w-full items-center justify-center gap-2.5 rounded-md border bg-background px-4 py-2.5 text-sm font-medium shadow-sm transition-colors hover:bg-accent"
                    >
                      <MicrosoftIcon className="h-[18px] w-[18px]" />
                      {tAuth("continueWithMicrosoft")}
                    </a>
                  )}
                </div>
              </div>
            )}

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
