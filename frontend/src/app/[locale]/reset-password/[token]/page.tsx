"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { ArrowRight, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { AuthShell } from "@/components/marketing/auth-shell";
import { api, ApiError } from "@/lib/api";

/**
 * /[locale]/reset-password/[token] — confirm step of the
 * forgot-password flow.
 *
 * No client-side preview round-trip: we just render the form
 * immediately. The token's validity is checked only on submit, and the
 * backend distinguishes 404 (never existed) from 410 (used / expired)
 * so the UI can render a "dead link" state with the right copy on
 * either. This avoids leaking token validity via a separate preview
 * endpoint that an attacker could enumerate.
 */

interface PageProps {
  params: Promise<{ locale: string; token: string }>;
}

export default function ResetPasswordPage({ params }: PageProps) {
  const { token } = use(params);
  const t = useTranslations("auth");
  const tMarketing = useTranslations("marketing");
  const router = useRouter();
  const locale = useLocale();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deadLink, setDeadLink] = useState<"gone" | "missing" | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError(t("passwordMismatch"));
      return;
    }
    setBusy(true);
    try {
      await api.confirmPasswordReset(token, password);
      router.push(`/${locale}/login?reset=success`);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 404) {
          setDeadLink("missing");
          return;
        }
        if (err.status === 410) {
          setDeadLink("gone");
          return;
        }
      }
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  }

  if (deadLink) {
    return (
      <AuthShell brand={<ResetBrand />}>
        <div className="space-y-6">
          <div className="grid h-12 w-12 place-items-center rounded-full bg-destructive/10 text-destructive">
            <ShieldAlert className="h-6 w-6" />
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold tracking-tight">
              {t(deadLink === "gone" ? "resetGoneTitle" : "resetMissingTitle")}
            </h2>
            <p className="text-sm text-muted-foreground">
              {t(deadLink === "gone" ? "resetGoneBody" : "resetMissingBody")}
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button asChild variant="outline" className="sm:flex-1">
              <Link href={`/${locale}/login`}>{tMarketing("backToLogin")}</Link>
            </Button>
            <Button asChild className="sm:flex-1">
              <Link href={`/${locale}/forgot-password`}>
                {t("resetRequestNew")}
              </Link>
            </Button>
          </div>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell brand={<ResetBrand />}>
      <div className="space-y-6">
        <div className="space-y-1">
          <h2 className="text-2xl font-semibold tracking-tight">{t("resetTitle")}</h2>
          <p className="text-sm text-muted-foreground">{t("resetSubtitle")}</p>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="password">{t("newPassword")}</Label>
            <PasswordInput
              id="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              visibilityLabels={{ show: t("showPassword"), hide: t("hidePassword") }}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm">{t("confirmPassword")}</Label>
            <PasswordInput
              id="confirm"
              autoComplete="new-password"
              required
              minLength={8}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              visibilityLabels={{ show: t("showPassword"), hide: t("hidePassword") }}
            />
          </div>
          {error && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
          <Button type="submit" className="group w-full" disabled={busy} size="lg">
            {busy ? t("resetSubmitting") : t("resetSubmit")}
            {!busy && <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />}
          </Button>
        </form>
      </div>
    </AuthShell>
  );
}

function ResetBrand() {
  const t = useTranslations("auth");
  return (
    <div className="space-y-5">
      <h1 className="bg-gradient-to-br from-foreground via-foreground to-foreground/60 bg-clip-text text-4xl font-semibold leading-tight tracking-tight text-transparent sm:text-5xl">
        {t("resetHeroTitle")}
      </h1>
      <p className="max-w-md text-base text-muted-foreground sm:text-lg">
        {t("resetHeroSubtitle")}
      </p>
    </div>
  );
}
