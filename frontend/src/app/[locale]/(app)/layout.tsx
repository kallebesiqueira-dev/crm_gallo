"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { AlertTriangle, TrendingUp } from "lucide-react";
import { Sidebar } from "@/components/sidebar";
import { LanguageSwitcher } from "@/components/language-switcher";
import { ThemeToggle } from "@/components/theme-toggle";
import { ConfirmProvider } from "@/components/confirm-dialog";
import { PlanBadge } from "@/components/plan-badge";
import { OrgSwitcher } from "@/components/org-switcher";
import { NotificationsBell } from "@/components/notifications-bell";
import { Button } from "@/components/ui/button";
import { api, setUnauthorizedHandler, type BillingMe, type User } from "@/lib/api";
import { clearToken, getToken, isExpired, onTokenChange } from "@/lib/auth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const locale = useLocale();
  const tAuth = useTranslations("auth");
  const tBilling = useTranslations("billing");
  const [user, setUser] = useState<User | null>(null);
  const [billing, setBilling] = useState<BillingMe | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      router.replace(`/${locale}/login`);
    });
    return () => setUnauthorizedHandler(null);
  }, [locale, router]);

  useEffect(() => {
    const off = onTokenChange((t) => {
      if (!t) router.replace(`/${locale}/login`);
    });
    return off;
  }, [locale, router]);

  useEffect(() => {
    const token = getToken();
    if (!token || isExpired(token)) {
      clearToken();
      router.replace(`/${locale}/login`);
      return;
    }
    api
      .me(token)
      .then((u) => {
        setUser(u);
        setReady(true);
      })
      .catch(() => {
        clearToken();
        router.replace(`/${locale}/login`);
      });
    api.billingMe(token).then(setBilling).catch(() => setBilling(null));
  }, [router, locale]);

  async function logout() {
    const token = getToken();
    if (token) {
      try {
        await api.logout(token);
      } catch {
        /* server-side audit is best-effort; client always clears local state */
      }
    }
    clearToken();
    router.replace(`/${locale}/login`);
  }

  if (!ready) {
    return (
      <div className="grid min-h-screen place-items-center text-muted-foreground">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-foreground" />
      </div>
    );
  }

  // Trial / seat-limit / canceled banners.
  const banner = billingBanner(billing, locale, tBilling);

  return (
    <ConfirmProvider>
      <div className="flex min-h-screen bg-muted/30">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="relative z-50 flex flex-wrap items-center justify-between gap-3 border-b bg-background px-6 py-3">
            <div className="flex items-center gap-3">
              {/* Org switcher hides itself when the user has 0–1 memberships,
                  so single-tenant installs see the same chrome as before. */}
              <OrgSwitcher activeOrgId={user?.last_active_org_id ?? null} />
              <div className="text-sm text-muted-foreground">{user?.email}</div>
              {billing && <PlanBadge plan={billing.plan} />}
            </div>
            <div className="flex items-center gap-2">
              {/* Bell sits leftmost in the right cluster — first
                  thing the user looks at when they're checking for
                  new work. Polls /counts every 60s + on focus. */}
              <NotificationsBell />
              <LanguageSwitcher />
              <ThemeToggle />
              <Button variant="ghost" size="sm" onClick={logout}>
                {tAuth("logout")}
              </Button>
            </div>
          </header>

          {banner}

          <main className="flex-1 p-6">{children}</main>
        </div>
      </div>
    </ConfirmProvider>
  );
}

function billingBanner(
  billing: BillingMe | null,
  locale: string,
  t: (k: string) => string,
): React.ReactNode {
  if (!billing) return null;

  const trialEnds = billing.trial_ends_at ? new Date(billing.trial_ends_at) : null;
  const trialDaysLeft = trialEnds
    ? Math.max(0, Math.ceil((trialEnds.getTime() - Date.now()) / (1000 * 60 * 60 * 24)))
    : null;

  if (trialDaysLeft !== null && trialDaysLeft > 0 && trialDaysLeft <= 7) {
    return (
      <Banner tone="info" href={`/${locale}/billing`} cta={t("manageBilling")}>
        <TrendingUp className="h-4 w-4" />
        {t("trialEndingSoon").replace("{days}", String(trialDaysLeft))}
      </Banner>
    );
  }

  if (
    billing.plan === "free" &&
    billing.seat_limit !== null &&
    billing.seats_remaining !== null &&
    billing.seats_remaining === 0
  ) {
    return (
      <Banner tone="warn" href={`/${locale}/billing`} cta={t("upgrade")}>
        <AlertTriangle className="h-4 w-4" />
        {t("seatLimitReachedBanner")}
      </Banner>
    );
  }

  if (billing.plan_canceled_at) {
    return (
      <Banner tone="warn" href={`/${locale}/billing`} cta={t("manageBilling")}>
        <AlertTriangle className="h-4 w-4" />
        {t("canceledBanner")}
      </Banner>
    );
  }

  return null;
}

function Banner({
  tone,
  children,
  href,
  cta,
}: {
  tone: "info" | "warn";
  children: React.ReactNode;
  href: string;
  cta: string;
}) {
  const cls =
    tone === "warn"
      ? "border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-200"
      : "border-primary/30 bg-primary/5 text-foreground";
  return (
    <div className={`flex items-center justify-between gap-3 border-b px-6 py-2 text-sm ${cls}`}>
      <div className="flex items-center gap-2">{children}</div>
      <Button asChild size="sm" variant={tone === "warn" ? "default" : "outline"}>
        <Link href={href}>{cta}</Link>
      </Button>
    </div>
  );
}
