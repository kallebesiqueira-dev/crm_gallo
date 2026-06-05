"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { ArrowRight, ShieldAlert } from "lucide-react";
import { Logo } from "@/components/logo";
import { LanguageSwitcher } from "@/components/language-switcher";
import { MfaCard } from "@/components/mfa-card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { clearToken } from "@/lib/auth";

/**
 * Forced MFA enrollment. Reached when /login answers `mfa_setup_required`
 * (a privileged user without a second factor, policy on). The session
 * cookies are already set, so this page can hit /mfa/setup + /mfa/enable
 * — but every tenant-data endpoint stays 403 until enrollment completes.
 *
 * Deliberately OUTSIDE the (app) layout: it makes no tenant-data calls,
 * so it never trips its own gate (which would loop the global redirect).
 */
export default function MfaSetupPage() {
  const t = useTranslations("mfa");
  const tApp = useTranslations("app");
  const locale = useLocale();
  const router = useRouter();
  const [enrolled, setEnrolled] = useState(false);

  async function signOut() {
    try {
      await api.logout("");
    } catch {
      /* best-effort; we clear locally regardless */
    }
    clearToken();
    router.replace(`/${locale}/login`);
  }

  return (
    <div className="min-h-screen bg-muted/30">
      <header className="flex items-center justify-between border-b bg-background px-6 py-4">
        <Logo href={`/${locale}/dashboard`} size="md" label={tApp("name")} />
        <LanguageSwitcher />
      </header>

      <main className="mx-auto w-full max-w-2xl px-4 py-10">
        <div className="mb-6 flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
          <div className="space-y-1">
            <h1 className="text-lg font-semibold">{t("forcedTitle")}</h1>
            <p className="text-sm text-muted-foreground">{t("forcedSubtitle")}</p>
          </div>
        </div>

        <MfaCard onEnabled={() => setEnrolled(true)} />

        <div className="mt-6 flex items-center justify-between">
          <Button variant="ghost" onClick={signOut}>
            {t("forcedSignOut")}
          </Button>
          <Button
            className="group"
            disabled={!enrolled}
            onClick={() => router.replace(`/${locale}/dashboard`)}
          >
            {t("forcedContinue")}
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </Button>
        </div>
      </main>
    </div>
  );
}
