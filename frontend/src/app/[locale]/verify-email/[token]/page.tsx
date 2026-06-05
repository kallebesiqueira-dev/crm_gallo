"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { CheckCircle2, Loader2, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AuthShell } from "@/components/marketing/auth-shell";
import { api, ApiError } from "@/lib/api";
import { setToken } from "@/lib/auth";

/**
 * /[locale]/verify-email/[token] — confirm step of the email-verification
 * flow (mirrors reset-password/[token]).
 *
 * On mount we POST the token to /verify-email/confirm. On success the
 * backend marks the email verified AND starts a session (sets cookies)
 * and returns an AuthResponse, so we store the access token and redirect
 * straight to the dashboard. The backend distinguishes 404 (never
 * existed) from 410 (used / expired) so we can render a precise dead-link
 * state.
 */

interface PageProps {
  params: Promise<{ locale: string; token: string }>;
}

type Phase = "loading" | "success" | "gone" | "missing" | "error";

export default function VerifyEmailPage({ params }: PageProps) {
  const { token } = use(params);
  const t = useTranslations("auth");
  const tMarketing = useTranslations("marketing");
  const router = useRouter();
  const locale = useLocale();

  const [phase, setPhase] = useState<Phase>("loading");
  // React 18 Strict Mode double-invokes effects in dev; the token is
  // single-use, so a second confirm would 410. Guard so the first
  // outcome wins and we don't flip a success into a "gone".
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    let active = true;
    (async () => {
      try {
        const res = await api.verifyEmailConfirm(token);
        if (!active) return;
        setToken(res.token.access_token);
        setPhase("success");
        router.replace(`/${res.user.locale || locale}/dashboard`);
      } catch (err) {
        if (!active) return;
        if (err instanceof ApiError) {
          if (err.status === 404) {
            setPhase("missing");
            return;
          }
          if (err.status === 410) {
            setPhase("gone");
            return;
          }
        }
        setPhase("error");
      }
    })();
    return () => {
      active = false;
    };
  }, [token, locale, router]);

  if (phase === "loading" || phase === "success") {
    return (
      <AuthShell brand={<VerifyBrand />}>
        <div className="space-y-6">
          <div className="grid h-12 w-12 place-items-center rounded-full bg-primary/10 text-primary">
            {phase === "success" ? (
              <CheckCircle2 className="h-6 w-6" />
            ) : (
              <Loader2 className="h-6 w-6 animate-spin" />
            )}
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold tracking-tight">
              {t(phase === "success" ? "verifySuccessTitle" : "verifyLoadingTitle")}
            </h2>
            <p className="text-sm text-muted-foreground">
              {t(phase === "success" ? "verifySuccessBody" : "verifyLoadingBody")}
            </p>
          </div>
        </div>
      </AuthShell>
    );
  }

  // Dead-link / error states.
  const titleKey =
    phase === "gone"
      ? "verifyGoneTitle"
      : phase === "missing"
        ? "verifyMissingTitle"
        : "verifyErrorTitle";
  const bodyKey =
    phase === "gone"
      ? "verifyGoneBody"
      : phase === "missing"
        ? "verifyMissingBody"
        : "verifyErrorBody";

  return (
    <AuthShell brand={<VerifyBrand />}>
      <div className="space-y-6">
        <div className="grid h-12 w-12 place-items-center rounded-full bg-destructive/10 text-destructive">
          <ShieldAlert className="h-6 w-6" />
        </div>
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold tracking-tight">{t(titleKey)}</h2>
          <p className="text-sm text-muted-foreground">{t(bodyKey)}</p>
        </div>
        <Button asChild variant="outline" className="w-full">
          <Link href={`/${locale}/login`}>{tMarketing("backToLogin")}</Link>
        </Button>
      </div>
    </AuthShell>
  );
}

function VerifyBrand() {
  const t = useTranslations("auth");
  return (
    <div className="space-y-5">
      <h1 className="bg-gradient-to-br from-foreground via-foreground to-foreground/60 bg-clip-text text-4xl font-semibold leading-tight tracking-tight text-transparent sm:text-5xl">
        {t("verifyHeroTitle")}
      </h1>
      <p className="max-w-md text-base text-muted-foreground sm:text-lg">
        {t("verifyHeroSubtitle")}
      </p>
    </div>
  );
}
