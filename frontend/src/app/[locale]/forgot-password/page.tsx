"use client";

import { useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { ArrowLeft, MailCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthShell } from "@/components/marketing/auth-shell";
import { api } from "@/lib/api";

/**
 * Forgot-password request page.
 *
 * Always renders the "we sent you a link" success state on submit,
 * regardless of whether the email was registered — the backend mirrors
 * this no-enumeration contract by returning 204 either way. The UI
 * shouldn't reveal anything the API doesn't.
 */
export default function ForgotPasswordPage() {
  const t = useTranslations("auth");
  const tMarketing = useTranslations("marketing");
  const locale = useLocale();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.requestPasswordReset(email);
    } catch {
      // We deliberately do NOT surface errors to the user — the
      // backend already swallows missing-email into a 204, and any
      // 4xx here (e.g. malformed email after client validation) is
      // already caught by `type=email + required`. A 5xx is rare and
      // showing it would muddy the "we always sent a link" contract.
    } finally {
      setSent(true);
      setBusy(false);
    }
  }

  return (
    <AuthShell
      brand={
        <div className="space-y-6">
          <h1 className="bg-gradient-to-br from-foreground via-foreground to-foreground/60 bg-clip-text text-4xl font-semibold leading-tight tracking-tight text-transparent sm:text-5xl">
            {t("forgotHeroTitle")}
          </h1>
          <p className="max-w-md text-base text-muted-foreground sm:text-lg">
            {t("forgotHeroSubtitle")}
          </p>
          <Link
            href={`/${locale}/login`}
            className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            {tMarketing("backToLogin")}
          </Link>
        </div>
      }
    >
      {sent ? (
        <div className="space-y-6">
          <div className="grid h-12 w-12 place-items-center rounded-full bg-emerald-500/10 text-emerald-500">
            <MailCheck className="h-6 w-6" />
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold tracking-tight">
              {t("forgotSentTitle")}
            </h2>
            <p className="text-sm text-muted-foreground">
              {t("forgotSentBody")}
            </p>
          </div>
          <p className="text-xs text-muted-foreground">{t("forgotSentNote")}</p>
          <Button asChild variant="outline" className="w-full">
            <Link href={`/${locale}/login`}>{tMarketing("backToLogin")}</Link>
          </Button>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="space-y-1">
            <h2 className="text-2xl font-semibold tracking-tight">
              {t("forgotTitle")}
            </h2>
            <p className="text-sm text-muted-foreground">{t("forgotSubtitle")}</p>
          </div>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">{t("email")}</Label>
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
            <Button type="submit" className="w-full" disabled={busy} size="lg">
              {busy ? t("forgotSending") : t("forgotSubmit")}
            </Button>
          </form>
        </div>
      )}
    </AuthShell>
  );
}
