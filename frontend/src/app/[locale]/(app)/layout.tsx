"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { AlertTriangle, HelpCircle, Mail, Search, Sparkles, TrendingUp } from "lucide-react";
import { Sidebar } from "@/components/sidebar";
import { MobileNav } from "@/components/mobile-nav";
import { LanguageSwitcher } from "@/components/language-switcher";
import { ThemeToggle } from "@/components/theme-toggle";
import { ConfirmProvider } from "@/components/confirm-dialog";
import { PlanBadge } from "@/components/plan-badge";
import { OrgSwitcher } from "@/components/org-switcher";
import { NotificationsBell } from "@/components/notifications-bell";
import { AssistantPanel } from "@/components/assistant-panel";
import { AvatarUpload } from "@/components/avatar-upload";
import { SupportDialog } from "@/components/support-dialog";
import { GlobalSearch } from "@/components/global-search";
import { Button } from "@/components/ui/button";
import {
  api,
  setMfaEnrollmentHandler,
  setUnauthorizedHandler,
  type BillingMe,
  type User,
} from "@/lib/api";
import { clearToken, getToken, isExpired, onTokenChange } from "@/lib/auth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const locale = useLocale();
  const tAuth = useTranslations("auth");
  const tBilling = useTranslations("billing");
  const tNav = useTranslations("nav");
  const tSearch = useTranslations("search");
  const [user, setUser] = useState<User | null>(null);
  const [billing, setBilling] = useState<BillingMe | null>(null);
  const [ready, setReady] = useState(false);
  const [supportOpen, setSupportOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      router.replace(`/${locale}/login`);
    });
    // Privileged user without MFA: server gates every data endpoint with
    // 403 `mfa_enrollment_required`. Send them to forced enrollment.
    setMfaEnrollmentHandler(() => {
      router.replace(`/${locale}/mfa-setup`);
    });
    return () => {
      setUnauthorizedHandler(null);
      setMfaEnrollmentHandler(null);
    };
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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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

  // Topbar: identity bits for the avatar.
  const fullName = user?.full_name || user?.email || "";
  const initials =
    fullName
      .split(" ")
      .map((p) => p[0])
      .join("")
      .slice(0, 2)
      .toUpperCase() || "U";
  const roleLabel = user?.role
    ? user.role.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : "";

  return (
    <ConfirmProvider>
      <div className="flex min-h-screen bg-muted/30">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-50 flex h-16 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur-xl sm:px-6">
            {/* Left — hamburger (mobile) + current section + org switcher */}
            <div className="flex min-w-0 items-center gap-2 sm:gap-3">
              <MobileNav />
              <div className="hidden sm:block">
                <OrgSwitcher activeOrgId={user?.last_active_org_id ?? null} />
              </div>
            </div>

            {/* Center — global search; opens the ⌘K command palette */}
            <button
              type="button"
              onClick={() => setSearchOpen(true)}
              className="mr-auto hidden w-full max-w-[18rem] items-center gap-2 rounded-xl border border-input bg-muted/50 px-3.5 py-2 text-left text-sm text-muted-foreground transition hover:border-primary/40 md:flex"
            >
              <Search className="h-4 w-4 shrink-0" />
              <span className="flex-1 truncate">{tSearch("placeholder")}</span>
              <kbd className="hidden shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] font-medium lg:inline">
                ⌘K
              </kbd>
            </button>

            {/* Right — actions + identity */}
            <div className="ml-auto flex items-center gap-1 sm:gap-1.5">
              <Link
                href={`/${locale}/inbox`}
                aria-label="Messaggi"
                className="hidden h-9 w-9 place-items-center rounded-lg text-muted-foreground transition hover:bg-accent hover:text-foreground sm:grid"
              >
                <Mail className="h-5 w-5" />
              </Link>
              <NotificationsBell />
              {/* Assistant slide-out — visible on every width since the page
                  left the nav (mobile must keep an entry point). */}
              <button
                type="button"
                onClick={() => setAssistantOpen(true)}
                aria-label={tNav("assistant")}
                title={tNav("assistant")}
                className="grid h-9 w-9 place-items-center rounded-lg text-muted-foreground transition hover:bg-accent hover:text-foreground"
              >
                <Sparkles className="h-5 w-5" />
              </button>
              <button
                type="button"
                onClick={() => setSupportOpen(true)}
                aria-label="Aiuto"
                className="hidden h-9 w-9 place-items-center rounded-lg text-muted-foreground transition hover:bg-accent hover:text-foreground sm:grid"
              >
                <HelpCircle className="h-5 w-5" />
              </button>
              <ThemeToggle />
              <LanguageSwitcher />
              {billing && (
                <span className="hidden sm:inline-flex">
                  <PlanBadge plan={billing.plan} />
                </span>
              )}
              <div className="ml-1 flex items-center gap-2 border-l border-border pl-2">
                {user ? (
                  <AvatarUpload entityType="user" entityId={user.id} fallback={initials} size={36} />
                ) : (
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500 text-sm font-semibold text-white">
                    {initials}
                  </span>
                )}
                <div className="hidden leading-tight xl:block">
                  <div className="max-w-[9rem] truncate text-sm font-semibold">{fullName}</div>
                  <div className="text-[11px] text-muted-foreground">{roleLabel}</div>
                </div>
              </div>
              <Button variant="ghost" size="sm" onClick={logout}>
                {tAuth("logout")}
              </Button>
            </div>
          </header>

          {banner}

          <main className="flex-1 p-3 sm:p-6">{children}</main>
        </div>
      </div>
      <SupportDialog open={supportOpen} onClose={() => setSupportOpen(false)} />
      <GlobalSearch open={searchOpen} onClose={() => setSearchOpen(false)} />
      <AssistantPanel open={assistantOpen} onClose={() => setAssistantOpen(false)} />
    </ConfirmProvider>
  );
}

function billingBanner(
  billing: BillingMe | null,
  locale: string,
  t: (key: string, values?: Record<string, string | number>) => string,
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
        {t("trialEndingSoon", { days: trialDaysLeft })}
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
