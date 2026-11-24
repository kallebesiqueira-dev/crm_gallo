"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { AlertTriangle, CreditCard, HelpCircle, LogOut, Mail, Search, Settings, Sparkles, TrendingUp } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@radix-ui/react-dropdown-menu";
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
import { ShortcutsHelp } from "@/components/shortcuts-help";
import { TourGuide } from "@/components/tour-guide";
import { CurrencyProvider } from "@/components/currency-provider";
import { Button } from "@/components/ui/button";
import {
  api,
  setMfaEnrollmentHandler,
  setUnauthorizedHandler,
  type BillingMe,
  type User,
} from "@/lib/api";
import { clearToken, getToken, isExpired, onTokenChange } from "@/lib/auth";

const menuItemClass =
  "flex h-9 cursor-pointer items-center gap-2.5 rounded-lg px-2.5 text-sm outline-none data-[highlighted]:bg-accent";

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
  const [assistantPrompt, setAssistantPrompt] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);

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
        // Keep the persisted locale in sync with the UI locale so server-side
        // AI (lead scoring, summaries) answers in the language the user is
        // actually viewing — not a stale default from signup (e.g. "it").
        if (u.locale !== locale) {
          api.updateMe(token, { locale }).catch(() => {});
        }
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
        return;
      }
      // "?" opens the keyboard-shortcuts help — but never while the user is
      // typing into a field (where "?" is a literal character).
      if (e.key === "?" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const el = document.activeElement as HTMLElement | null;
        const typing =
          !!el &&
          (el.tagName === "INPUT" ||
            el.tagName === "TEXTAREA" ||
            el.tagName === "SELECT" ||
            el.isContentEditable);
        if (!typing) {
          e.preventDefault();
          setHelpOpen(true);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // The dashboard AI card (and its chips) opens the assistant via this event.
  useEffect(() => {
    const onOpen = (e: Event) => {
      const detail = (e as CustomEvent<{ prompt?: string }>).detail;
      setAssistantPrompt(detail?.prompt ?? "");
      setAssistantOpen(true);
    };
    window.addEventListener("gallo:assistant-open", onOpen);
    return () => window.removeEventListener("gallo:assistant-open", onOpen);
  }, []);

  // "Go to" leader shortcuts: press G then D/H/L/C/P/T to jump to a section
  // (ignored while typing in a field).
  useEffect(() => {
    const GOTO: Record<string, string> = {
      d: "dashboard",
      h: "hoje",
      l: "leads",
      c: "customers",
      p: "pipeline",
      t: "tasks",
    };
    let leader = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement as HTMLElement | null;
      const typing =
        !!el &&
        (el.tagName === "INPUT" ||
          el.tagName === "TEXTAREA" ||
          el.tagName === "SELECT" ||
          el.isContentEditable);
      if (typing || e.metaKey || e.ctrlKey || e.altKey) {
        leader = false;
        return;
      }
      if (leader) {
        leader = false;
        clearTimeout(timer);
        const dest = GOTO[e.key.toLowerCase()];
        if (dest) {
          e.preventDefault();
          router.push(`/${locale}/${dest}`);
        }
        return;
      }
      if (e.key.toLowerCase() === "g") {
        leader = true;
        clearTimeout(timer);
        timer = setTimeout(() => {
          leader = false;
        }, 1500);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      clearTimeout(timer);
    };
  }, [locale, router]);

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
      <div className="grid min-h-dvh place-items-center text-muted-foreground">
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
      <CurrencyProvider initial={user?.display_currency ?? "EUR"} locale={locale}>
      <div className="flex min-h-dvh bg-muted/30">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-50 flex h-14 items-center gap-2 border-b bg-background/80 px-3 backdrop-blur-xl sm:px-4">
            <div className="flex shrink-0 items-center gap-2">
              <MobileNav />
              <div className="hidden sm:block">
                <OrgSwitcher activeOrgId={user?.last_active_org_id ?? null} />
              </div>
            </div>

            <button
              type="button"
              onClick={() => setSearchOpen(true)}
              className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-full border border-input bg-muted/50 px-3 text-left text-sm text-muted-foreground transition hover:border-primary/40 md:max-w-md"
            >
              <Search className="h-4 w-4 shrink-0" />
              <span className="flex-1 truncate">{tSearch("placeholder")}</span>
              <kbd className="hidden shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] font-medium lg:inline">
                ⌘K
              </kbd>
            </button>

            <div className="ml-auto flex shrink-0 items-center gap-1.5">
              <div className="flex items-center rounded-full border bg-muted/40 p-0.5">
                <Link
                  href={`/${locale}/inbox`}
                  aria-label={tNav("inbox")}
                  className="hidden h-8 w-8 place-items-center rounded-full text-muted-foreground transition hover:bg-background hover:text-foreground sm:grid"
                >
                  <Mail className="h-4 w-4" />
                </Link>
                <NotificationsBell />
                <button
                  type="button"
                  data-tour="assistant"
                  onClick={() => {
                    setAssistantPrompt("");
                    setAssistantOpen(true);
                  }}
                  aria-label={tNav("assistant")}
                  className="grid h-8 w-8 place-items-center rounded-full text-muted-foreground transition hover:bg-background hover:text-foreground"
                >
                  <Sparkles className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setSupportOpen(true)}
                  aria-label="Help"
                  className="hidden h-8 w-8 place-items-center rounded-full text-muted-foreground transition hover:bg-background hover:text-foreground sm:grid"
                >
                  <HelpCircle className="h-4 w-4" />
                </button>
              </div>
              <LanguageSwitcher />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className="flex h-9 items-center gap-2 rounded-full border bg-background py-0.5 pl-0.5 pr-2 text-left transition hover:bg-accent"
                    aria-label={fullName}
                  >
                    {user ? (
                      <AvatarUpload entityType="user" entityId={user.id} fallback={initials} size={28} />
                    ) : (
                      <span className="grid h-7 w-7 place-items-center rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500 text-xs font-semibold text-white">
                        {initials}
                      </span>
                    )}
                    <span className="hidden max-w-[7rem] truncate text-sm font-medium sm:inline">{fullName}</span>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="end"
                  sideOffset={8}
                  className="z-50 w-64 rounded-xl border bg-popover p-1.5 shadow-lg"
                >
                  <div className="flex items-center gap-3 px-2.5 py-2">
                    {user ? (
                      <AvatarUpload entityType="user" entityId={user.id} fallback={initials} size={36} />
                    ) : (
                      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500 text-xs font-semibold text-white">
                        {initials}
                      </span>
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold leading-5">{fullName}</div>
                      <div className="truncate text-xs leading-5 text-muted-foreground">{roleLabel}</div>
                      {billing ? (
                        <div className="mt-1">
                          <PlanBadge plan={billing.plan} />
                        </div>
                      ) : null}
                    </div>
                  </div>
                  <div className="mx-2 my-1 h-px bg-border" role="separator" />
                  <DropdownMenuItem className={menuItemClass} onSelect={() => router.push(`/${locale}/settings`)}>
                    <Settings className="h-4 w-4 shrink-0 text-muted-foreground" />
                    {tNav("settings")}
                  </DropdownMenuItem>
                  <DropdownMenuItem className={menuItemClass} onSelect={() => router.push(`/${locale}/billing`)}>
                    <CreditCard className="h-4 w-4 shrink-0 text-muted-foreground" />
                    {tNav("billing")}
                  </DropdownMenuItem>
                  <ThemeToggle variant="menu" />
                  <div className="mx-2 my-1 h-px bg-border" role="separator" />
                  <DropdownMenuItem
                    className={`${menuItemClass} text-rose-600 data-[highlighted]:bg-rose-500/10 data-[highlighted]:text-rose-700 dark:text-rose-400`}
                    onSelect={() => logout()}
                  >
                    <LogOut className="h-4 w-4 shrink-0" />
                    {tAuth("logout")}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </header>

          {banner}

          <main className="flex-1 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:p-6 sm:pb-[max(1.5rem,env(safe-area-inset-bottom))]">{children}</main>
        </div>
      </div>
      <SupportDialog open={supportOpen} onClose={() => setSupportOpen(false)} />
      <GlobalSearch open={searchOpen} onClose={() => setSearchOpen(false)} />
      <ShortcutsHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
      <TourGuide />
      <AssistantPanel
        open={assistantOpen}
        initialPrompt={assistantPrompt}
        onClose={() => {
          setAssistantOpen(false);
          setAssistantPrompt("");
        }}
      />
      </CurrencyProvider>
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
