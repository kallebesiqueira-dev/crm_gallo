"use client";

import { Suspense, useEffect, useState, type ComponentType } from "react";
import dynamic from "next/dynamic";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import {
  ArrowDownUp,
  ArrowRight,
  ArrowUpRight,
  Award,
  BarChart3,
  Brain,
  Check,
  CheckCheck,
  Code2,
  FileSignature,
  FileText,
  Gauge,
  Headset,
  KanbanSquare,
  LayoutGrid,
  ShieldCheck,
  Sparkles,
  UserCheck,
  UserPlus,
  Users,
  Webhook,
  Workflow,
  Zap,
} from "lucide-react";
import { WhatsAppIcon } from "@/components/whatsapp-icon";
import { Button } from "@/components/ui/button";
import { LanguageSwitcher } from "@/components/language-switcher";
import { DashboardVideo } from "@/components/marketing/dashboard-video";
import { FeatureSections } from "@/components/marketing/feature-section";
import { AboutSection } from "@/components/marketing/about-section";
import { ValuesSection } from "@/components/marketing/values-section";
import { ManifestoSection } from "@/components/marketing/manifesto-section";
import { ComparisonSection } from "@/components/marketing/comparison-section";
import { Reveal, RevealGroup } from "@/components/marketing/reveal";
import { FuturisticBackground } from "@/components/marketing/futuristic-background";
import { LandingSplash } from "@/components/marketing/landing-splash";
import { Footer } from "@/components/marketing/footer";
import { TiltCard } from "@/components/marketing/tilt-card";
import { Logo } from "@/components/logo";
import { SmoothScroll } from "@/components/marketing/smooth-scroll";
import { SearchParamWatcher } from "@/components/search-param-watcher";
import { api, type PlanOut, type PlanId, type BillingCycle } from "@/lib/api";
import { createPublicCheckoutSession } from "@/lib/public-api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

// Lazy + client-only: keeps the chatbot and its logic out of the first paint
// and the SSR HTML. The landing renders fully without it.
const LandingChatbot = dynamic(
  () => import("@/components/marketing/chatbot/landing-chatbot"),
  { ssr: false },
);

const PLAN_GRADIENT: Record<PlanId, string> = {
  free: "from-slate-500/10 to-slate-500/0",
  standard: "from-primary/20 to-blue-500/0",
  business: "from-violet-500/20 via-blue-500/10 to-violet-500/0",
  premium: "from-amber-500/20 via-fuchsia-500/10 to-pink-500/0",
};

// Per-feature icons (by plan + position) — a contextual glyph instead of a
// generic green check, matched to each feature's meaning. Order MUST mirror the
// FALLBACK_PLANS features arrays / the pricing.plans.<id>.features messages.
const FEATURE_ICONS: Record<PlanId, Array<ComponentType<{ className?: string }>>> = {
  free: [Users, LayoutGrid, UserPlus, KanbanSquare, Sparkles],
  standard: [Users, FileText, BarChart3, Gauge, Sparkles],
  business: [CheckCheck, FileSignature, ShieldCheck, Users, Workflow, ArrowDownUp, Brain],
  premium: [CheckCheck, WhatsAppIcon, Code2, Webhook, Zap, Sparkles, Headset, UserCheck],
};

// Static mirror of backend/app/billing/catalog.py. The public marketing page
// must always show prices even when the billing API isn't reachable (e.g.
// the frontend running without a backend). When the API responds, its data
// wins; this is only the fallback.
const FALLBACK_PLANS: PlanOut[] = [
  {
    id: "free",
    name: "Free",
    tagline: "Get started and validate with your team.",
    monthly_eur: 0,
    yearly_eur_per_user: 0,
    yearly_total_eur: 0,
    seat_limit: 2,
    ai_credits: 50,
    features: ["Up to 2 users", "Basic CRM", "Leads", "Pipeline", "Limited AI — 50 credits"],
    highlighted: false,
    requires_payment: false,
    trial_days: 0,
  },
  {
    id: "standard",
    name: "Standard",
    tagline: "For growing sales teams.",
    monthly_eur: 19,
    yearly_eur_per_user: 15.2,
    yearly_total_eur: 182.4,
    seat_limit: 10,
    ai_credits: 500,
    // Keep in sync with backend/app/billing/catalog.py (the source of truth
    // the /plans API serves) so this offline fallback matches production.
    features: ["Up to 10 users", "PDF proposals", "Reports", "Advanced dashboard", "AI — 500 credits"],
    highlighted: true,
    requires_payment: true,
    trial_days: 0,
  },
  {
    id: "business",
    name: "Business",
    tagline: "For teams closing deals end-to-end.",
    monthly_eur: 39,
    yearly_eur_per_user: 31.2,
    yearly_total_eur: 374.4,
    seat_limit: null,
    ai_credits: 2000,
    features: [
      "Everything in Standard",
      "E-signature",
      "Permissions",
      "Teams",
      "Basic automations",
      "Multiple pipelines",
      "AI — 2,000 credits",
    ],
    highlighted: false,
    requires_payment: true,
    trial_days: 0,
  },
  {
    id: "premium",
    name: "Premium",
    tagline: "For teams that scale with automation.",
    monthly_eur: 59,
    yearly_eur_per_user: 47.2,
    yearly_total_eur: 566.4,
    seat_limit: null,
    ai_credits: null,
    features: [
      "Everything in Business",
      "WhatsApp",
      "API",
      "Webhooks",
      "Unlimited automations",
      "Unlimited AI",
      "Priority support",
      "Dedicated account manager",
    ],
    highlighted: false,
    requires_payment: true,
    trial_days: 14,
  },
];

export default function PricingPage() {
  const t = useTranslations("pricing");
  const tApp = useTranslations("app");
  const tMarketing = useTranslations("marketing");
  const locale = useLocale();
  const router = useRouter();

  const [plans, setPlans] = useState<PlanOut[] | null>(null);
  const [cycle, setCycle] = useState<BillingCycle>("monthly");
  const [busyPlan, setBusyPlan] = useState<PlanId | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [stripeFlag, setStripeFlag] = useState<string | null>(null);

  // Framer Motion (Reveal/RevealGroup) drives every section's entry
  // animation now — see components/marketing/reveal.tsx. SmoothScroll
  // attaches Lenis to the document root, no per-page ref needed.

  useEffect(() => {
    api
      .plans()
      .then((p) => setPlans(p.length ? p : FALLBACK_PLANS))
      .catch(() => setPlans(FALLBACK_PLANS));
  }, []);

  // `?stripe=cancel` comes back from an abandoned Checkout — surface a
  // gentle banner. The flag is read by <SearchParamWatcher> below so
  // useSearchParams() stays inside its own Suspense boundary.
  useEffect(() => {
    if (stripeFlag === "cancel") {
      setBanner(t("checkoutCanceled"));
    }
  }, [stripeFlag, t]);

  // Whole monthly prices stay clean ("€19"); fractional yearly per-user prices
  // show their cents ("€15,20") so the −20% math is exact, never rounded off.
  const moneyWhole = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  });
  const moneyCents = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const money = (n: number) => (Number.isInteger(n) ? moneyWhole : moneyCents).format(n);

  async function handleChoose(plan: PlanOut) {
    if (!plan.requires_payment) {
      router.push(`/${locale}/register?plan=${plan.id}`);
      return;
    }
    const token = getToken();
    if (token) {
      // Authenticated: in-app, org-scoped upgrade.
      setBusyPlan(plan.id);
      setBanner(null);
      try {
        const { url } = await api.checkout(token, plan.id, cycle);
        window.location.assign(url);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Checkout failed";
        setBanner(
          msg.includes("503") || msg.toLowerCase().includes("not configured")
            ? t("stripeNotConfigured")
            : msg,
        );
        setBusyPlan(null);
      }
      return;
    }
    // Unauthenticated visitor — prefer a hosted Stripe Checkout link, then a
    // backend-created session (price validated server-side), then fall back to
    // free sign-up so the CTA always does something useful.
    const directUrl = process.env.NEXT_PUBLIC_STRIPE_CHECKOUT_URL;
    if (directUrl) {
      window.location.assign(directUrl);
      return;
    }
    setBusyPlan(plan.id);
    setBanner(null);
    try {
      const url = await createPublicCheckoutSession(plan.id, cycle);
      window.location.assign(url);
    } catch {
      setBusyPlan(null);
      router.push(`/${locale}/register?plan=${plan.id}&cycle=${cycle}`);
    }
  }

  return (
    <SmoothScroll>
    {/* Before first paint: if the splash hasn't played this session, hide the
        landing + paint the splash's dark bg, so the page never flashes before
        the <LandingSplash> overlay mounts. Removed when the intro fades. */}
    <script
      dangerouslySetInnerHTML={{
        __html:
          "try{if(!sessionStorage.getItem('gallo-splash-seen')){document.documentElement.classList.add('gallo-splash-pending')}}catch(e){}",
      }}
    />
    <LandingSplash />
    {/* `dark` on the root forces the landing into dark mode regardless of
        the user's theme preference — the rest of the app (auth, dashboard,
        etc.) still respects the toggle. <FuturisticBackground> is fixed to
        the viewport at z-0 and provides the actual base colour; every other
        page surface stacks above via `relative z-10` so it can't get hidden
        behind the mesh. */}
    <div data-landing-root className="dark relative min-h-screen overflow-x-clip text-foreground">
      <Suspense fallback={null}>
        <SearchParamWatcher name="stripe" onValue={setStripeFlag} />
      </Suspense>
      <FuturisticBackground />
      {/* Sticky header */}
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#040509]/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
          <Logo href="/" size="md" label={tApp("name")} />
          <nav className="hidden items-center gap-7 text-sm font-medium md:flex">
            {[
              { href: "#manifesto", label: tMarketing("navManifesto") },
              { href: "#about", label: tMarketing("navAbout") },
              { href: "#values", label: tMarketing("navValues") },
              { href: "#features", label: tMarketing("navFeatures") },
              { href: "#pricing", label: tMarketing("navPricing") },
              { href: "#faq", label: tMarketing("navFaq") },
            ].map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="group relative tracking-wide text-muted-foreground/90 transition-colors duration-300 hover:text-foreground"
              >
                {item.label}
                {/* Neon violet->fuchsia underline that slides in on hover —
                    picks up the page's gradient/futuristic theme. */}
                <span
                  aria-hidden
                  className="pointer-events-none absolute -bottom-1.5 left-0 h-px w-full origin-left scale-x-0 rounded-full bg-gradient-to-r from-violet-400 via-fuchsia-400 to-violet-400 shadow-[0_0_8px_rgba(167,139,250,0.7)] transition-transform duration-300 ease-out group-hover:scale-x-100"
                />
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            {/* No ThemeToggle on the landing — the page is forced dark via
                className="dark" on the root, so a light/dark switch here
                would do nothing visible and just confuse users. The toggle
                still lives in the auth shell and the authenticated app
                where the user's theme preference actually matters. */}
            <LanguageSwitcher />
            <Button asChild variant="ghost" size="sm">
              <Link href={`/${locale}/login`}>{t("signIn")}</Link>
            </Button>
            <Button asChild size="sm">
              <Link href={`/${locale}/register`}>{t("getStarted")}</Link>
            </Button>
          </div>
        </div>
      </header>

      {/* ============================== HERO (split: image left, text right) ============================== */}
      {/* Hero no longer carries its own ambient background — the page-level
          <FuturisticBackground> handles the mesh, grid, aurora drift and
          scanline beam for every section uniformly. */}
      <section className="relative overflow-hidden">

        <div className="mx-auto grid max-w-7xl gap-14 px-6 py-16 lg:grid-cols-2 lg:items-center lg:gap-20 lg:py-24">
          {/* LEFT — Gallo image with colored blob + dashed arc + floating badge.
              Lives in DOM-order first so mobile sees the visual first. */}
          <Reveal
            variant="scaleIn"
            standalone
            className="relative mx-auto flex w-full max-w-[480px] items-center justify-center"
          >
            <TiltCard max={12} glare={false} className="relative w-full">
            {/* Dashed outer ring */}
            <svg
              aria-hidden
              viewBox="0 0 512 512"
              className="absolute -inset-4 h-[calc(100%+2rem)] w-[calc(100%+2rem)] text-foreground/25"
              fill="none"
            >
              <circle cx="256" cy="256" r="252" stroke="currentColor" strokeWidth="1.5" strokeDasharray="6 9" />
            </svg>

            {/* Inner aspect-square so the colored blob and image scale together. */}
            <div className="relative aspect-square w-full">
              {/* Colored gradient blob */}
              <div className="absolute inset-0 rounded-full bg-gradient-to-br from-orange-500 via-rose-500 to-pink-500 shadow-2xl shadow-rose-500/30 dark:shadow-rose-500/40" />
              {/* Inner glossy highlight */}
              <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-transparent via-white/10 to-white/25 mix-blend-overlay" />

              {/* The gallo image, clipped to the circle. */}
              <div className="absolute inset-0 overflow-hidden rounded-full ring-1 ring-white/10">
                <Image
                  src="/gallo-hero.png"
                  alt="GALLO CRM dashboard"
                  fill
                  priority
                  sizes="(min-width: 1024px) 480px, 90vw"
                  className="object-cover object-center scale-105"
                />
              </div>

              {/* Floating "award" card */}
              <div className="absolute -bottom-5 -left-4 z-10 flex items-center gap-3 rounded-xl border bg-background/95 px-4 py-3 shadow-2xl backdrop-blur-xl sm:-left-8">
                <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-orange-500 to-rose-500 text-white shadow-lg shadow-orange-500/30">
                  <Award className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-semibold leading-tight">
                    {tMarketing("heroBadgeTitle")}
                  </div>
                  <div className="text-[10px] leading-tight text-muted-foreground">
                    {tMarketing("heroBadgeSubtitle")}
                  </div>
                </div>
              </div>

              {/* Floating "stat" chip */}
              <div className="absolute -right-2 top-6 z-10 hidden items-center gap-2 rounded-full border bg-background/95 px-3 py-1.5 text-[11px] font-medium shadow-xl backdrop-blur-xl sm:flex">
                <Sparkles className="h-3 w-3 text-violet-500" />
                <span>{t("heroBadge")}</span>
              </div>
            </div>
            </TiltCard>
          </Reveal>

          {/* RIGHT — text column. Single RevealGroup orchestrates the
              eyebrow → title → subtitle → CTAs → trust pill → divider
              cascade with the requested 120ms stagger and 1.6s curve. */}
          <RevealGroup className="relative flex flex-col">
            {/* "Hi there" eyebrow */}
            <Reveal variant="soft" className="flex items-center gap-2 text-sm">
              <span className="font-medium text-foreground/80">{tMarketing("heroEyebrow")}</span>
              <svg
                viewBox="0 0 24 24"
                className="h-5 w-5 -rotate-12 text-rose-500"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <path d="M3 17l8-8 4 4 6-6" />
                <path d="M14 7h7v7" />
              </svg>
            </Reveal>

            {/* Big headline with subtle animated glow behind it.
                The glow sits in the same stacking context but is decorative
                only (pointer-events-none, aria-hidden). */}
            <Reveal variant="title" className="relative mt-6">
              <span
                aria-hidden
                className="pointer-events-none absolute -inset-x-6 -inset-y-6 -z-10 rounded-[40px] bg-gradient-to-br from-blue-500/15 via-violet-500/10 to-fuchsia-500/15 blur-3xl animate-pulse-slow"
              />
              <h1 className="text-5xl font-bold leading-[1.05] tracking-tight sm:text-6xl lg:text-7xl">
                <span className="block text-foreground">{tMarketing("heroHeadlineLine1")}</span>
                {/* Bubble-inflate hover: the violet gradient line swells like
                    a soft balloon on mouse-over. inline-block hugs the text so
                    the scale pivots around the glyph centre, and the springy
                    cubic-bezier gives the motion that "inflating" feel. */}
                <span className="mt-1 inline-block bg-gradient-to-br from-blue-500 via-violet-500 to-fuchsia-500 bg-clip-text text-transparent drop-shadow-[0_2px_18px_rgba(99,102,241,0.25)] cursor-default transition-all duration-[650ms] ease-[cubic-bezier(0.34,1.56,0.64,1)] hover:scale-[1.06] hover:drop-shadow-[0_10px_50px_rgba(168,85,247,0.55)]">
                  {tMarketing("heroHeadlineLine2")}
                </span>
              </h1>
            </Reveal>

            <Reveal
              variant="text"
              className="mt-7 max-w-lg text-base leading-relaxed text-muted-foreground sm:text-lg"
            >
              {tMarketing("heroSubheadline")}
            </Reveal>

            {/* CTA — circle-arrow + label, matching reference's "My Services" */}
            <Reveal variant="button" className="mt-10 flex flex-wrap items-center gap-6">
              <Link
                href={`/${locale}/register`}
                className="group inline-flex items-center gap-4"
              >
                <span className="grid h-14 w-14 place-items-center rounded-full border-2 border-foreground/80 text-foreground transition-all duration-300 group-hover:scale-105 group-hover:border-foreground group-hover:bg-foreground group-hover:text-background group-hover:shadow-2xl group-hover:shadow-foreground/20">
                  <ArrowUpRight className="h-5 w-5 transition-transform duration-300 group-hover:rotate-45" />
                </span>
                <span className="text-base font-medium underline-offset-[6px] decoration-foreground/40 transition-all group-hover:underline">
                  {tMarketing("ctaPrimary")}
                </span>
              </Link>

              <a
                href="#pricing"
                className="group inline-flex items-center gap-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
              >
                {tMarketing("ctaSecondary")}
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </a>
            </Reveal>

            {/* Trust pill */}
            <Reveal
              variant="text"
              className="mt-8 inline-flex w-fit items-center gap-2 rounded-full border bg-card/60 px-3 py-1 text-xs text-muted-foreground backdrop-blur-xl"
            >
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
              {tMarketing("heroTrustline")}
            </Reveal>

            {/* Decorative divider — top border + horizontal gradient line */}
            <Reveal variant="soft" className="mt-14 flex items-center border-t pt-6">
              <div className="ml-auto h-px flex-1 max-w-[140px] bg-gradient-to-r from-border to-transparent" />
            </Reveal>
          </RevealGroup>
        </div>
      </section>

      {/* ============================== MANIFESTO (main objective) ============================== */}
      <ManifestoSection />

      {/* ============================== COMPARISON (Why Gallo) ============================== */}
      <ComparisonSection />

      {/* ============================== SHOWCASE (mockup) ============================== */}
      <section className="relative overflow-hidden py-16">
        {/* Layered ambient glow behind the dashboard so the reveal feels
            like the product itself is illuminating the page. */}
        <div
          aria-hidden
          className="pointer-events-none absolute left-1/2 top-1/2 -z-10 h-[36rem] w-[64rem] max-w-full -translate-x-1/2 -translate-y-1/2 rounded-full bg-gradient-to-br from-blue-500/15 via-violet-500/10 to-fuchsia-500/15 blur-3xl animate-pulse-slow"
        />
        <Reveal standalone variant="scaleIn" className="relative mx-auto max-w-6xl px-6">
          <DashboardVideo />
        </Reveal>
      </section>

      {/* ============================== ABOUT / CHI SIAMO ============================== */}
      <AboutSection />

      {/* ============================== VALUES / I NOSTRI VALORI ============================== */}
      <ValuesSection />

      {/* ============================== FEATURES ============================== */}
      <div id="features">
        <FeatureSections />
      </div>

      {/* ============================== PRICING ============================== */}
      <section id="pricing" className="relative overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-96 bg-gradient-to-b from-primary/5 to-transparent"
        />
        <div className="mx-auto max-w-6xl px-6 py-24">
          <RevealGroup className="text-center">
            <Reveal
              variant="soft"
              className="text-xs font-semibold uppercase tracking-[0.18em] text-primary"
            >
              {t("pricingEyebrow")}
            </Reveal>
            <Reveal variant="title" className="relative mt-3">
              <span
                aria-hidden
                className="pointer-events-none absolute -inset-x-12 -inset-y-6 -z-10 rounded-[60px] bg-gradient-to-br from-primary/15 via-violet-500/10 to-fuchsia-500/15 blur-3xl animate-pulse-slow"
              />
              <h2 className="text-3xl font-semibold tracking-tight sm:text-5xl">
                {t("heroTitle")}
              </h2>
            </Reveal>
            <Reveal
              variant="text"
              className="mx-auto mt-4 max-w-2xl text-base text-muted-foreground"
            >
              {t("heroSubtitle")}
            </Reveal>

            <Reveal variant="button" className="mt-10 inline-flex items-center rounded-full border bg-muted/40 p-1">
              <CycleTab active={cycle === "monthly"} onClick={() => setCycle("monthly")}>
                {t("monthly")}
              </CycleTab>
              <CycleTab active={cycle === "yearly"} onClick={() => setCycle("yearly")}>
                {t("yearly")}
                <span className="ml-1.5 rounded-full bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 dark:text-emerald-300">
                  -20%
                </span>
              </CycleTab>
            </Reveal>

            {banner && (
              <div className="mx-auto mt-8 max-w-md rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-900 dark:text-amber-200">
                {banner}
              </div>
            )}
          </RevealGroup>

          <RevealGroup
            className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4"
            stagger={0.12}
            delayChildren={0.15}
          >
            {plans === null && <PlanSkeleton count={3} />}
            {plans?.map((plan) => (
              <Reveal key={plan.id} variant="card" className="h-full">
                {/* Vitrine: each price card tilts in 3D toward the cursor with
                    a glass sheen — a little showroom for the plans. */}
                <TiltCard max={6} glare={false} className="h-full rounded-2xl">
                  <PlanCard
                    plan={plan}
                    cycle={cycle}
                    money={money}
                    busy={busyPlan === plan.id}
                    onChoose={() => handleChoose(plan)}
                  />
                </TiltCard>
              </Reveal>
            ))}
          </RevealGroup>

          <Reveal
            standalone
            variant="text"
            className="mt-8 flex flex-wrap items-center justify-center gap-2 text-center text-sm text-muted-foreground"
          >
            <ShieldCheck className="h-4 w-4 text-emerald-500" />
            <span>{tMarketing("securePayment")}</span>
            <span className="text-muted-foreground/40">·</span>
            <span>{tMarketing("noCardRequired")}</span>
            <span className="text-muted-foreground/40">·</span>
            <span>{tMarketing("vatIncluded")}</span>
          </Reveal>
        </div>
      </section>

      {/* ============================== COMPARE MATRIX ============================== */}
      {plans && plans.length > 0 && (
        <section>
          <RevealGroup className="mx-auto max-w-5xl px-6 py-20">
            <Reveal variant="soft">
              <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                {t("compareTitle")}
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">{t("compareSubtitle")}</p>
            </Reveal>

            <Reveal
              variant="card"
              className="mt-8 overflow-hidden rounded-2xl border bg-background shadow-sm"
            >
              {/* Mobile: the matrix scrolls sideways INSIDE this box so the
                  page itself never gets a horizontal scrollbar. min-width keeps
                  every column readable; on lg the table fits and scroll vanishes. */}
              <div className="overflow-x-auto overscroll-x-contain">
                <table className="w-full min-w-[640px] text-sm">
                <thead className="border-b bg-muted/30 text-xs uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-6 py-4 text-left font-medium">{t("feature")}</th>
                    {plans.map((p) => (
                      <th
                        key={p.id}
                        className={cn(
                          "px-6 py-4 text-center font-medium",
                          p.highlighted && "bg-primary/5 text-primary",
                        )}
                      >
                        {p.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {buildMatrix(plans, t, locale).map((row) => (
                    <tr key={row.label}>
                      <td className="px-6 py-3 font-medium">{row.label}</td>
                      {row.cells.map((cell, i) => (
                        <td
                          key={i}
                          className={cn(
                            "px-6 py-3 text-center text-muted-foreground",
                            plans[i].highlighted && "bg-primary/[0.03]",
                          )}
                        >
                          {cell === true ? (
                            <Check className="mx-auto h-4 w-4 text-primary" />
                          ) : cell === false ? (
                            <span className="text-muted-foreground/50">—</span>
                          ) : (
                            <span>{cell}</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
                </table>
              </div>
            </Reveal>
          </RevealGroup>
        </section>
      )}

      {/* ============================== FAQ ============================== */}
      <section id="faq">
        <div className="mx-auto max-w-3xl px-6 py-20">
          <Reveal standalone variant="title" className="relative text-center">
            <span
              aria-hidden
              className="pointer-events-none absolute -inset-x-10 -inset-y-6 -z-10 mx-auto h-32 max-w-md rounded-[60px] bg-gradient-to-br from-primary/15 via-violet-500/10 to-fuchsia-500/15 blur-3xl animate-pulse-slow"
            />
            <h2 className="text-3xl font-semibold tracking-tight">{t("faqTitle")}</h2>
          </Reveal>
          <RevealGroup className="mt-10 space-y-3" stagger={0.08}>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((i) => (
              <Reveal key={i} variant="card">
                <details
                  className="group rounded-xl border bg-background p-5 transition-all duration-[250ms] hover:-translate-y-0.5 hover:scale-[1.01] hover:border-primary/40 hover:shadow-lg"
                >
                  <summary className="flex cursor-pointer items-center justify-between text-sm font-medium">
                    {t(`faq.${i}.q`)}
                    <span className="ml-4 text-muted-foreground transition-transform group-open:rotate-180">⌄</span>
                  </summary>
                  <p className="mt-3 text-sm text-muted-foreground">{t(`faq.${i}.a`)}</p>
                </details>
              </Reveal>
            ))}
          </RevealGroup>
        </div>
      </section>

      {/* ============================== FINAL CTA ============================== */}
      <section className="relative overflow-hidden">
        <div
          aria-hidden
          className="absolute inset-0 -z-10 bg-gradient-to-b from-transparent via-primary/5 to-violet-500/10"
        />
        {/* Pulsing glow halo behind the final CTA */}
        <div
          aria-hidden
          className="pointer-events-none absolute left-1/2 top-1/2 -z-10 h-[28rem] w-[28rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-gradient-to-br from-primary/20 via-violet-500/15 to-fuchsia-500/20 blur-3xl animate-pulse-slow"
        />
        <RevealGroup className="mx-auto max-w-3xl px-6 py-24 text-center">
          <Reveal variant="title">
            <h2 className="text-3xl font-semibold tracking-tight sm:text-5xl">{t("ctaTitle")}</h2>
          </Reveal>
          <Reveal variant="text" className="mx-auto mt-4 max-w-xl text-muted-foreground">
            {t("ctaSubtitle")}
          </Reveal>
          <Reveal variant="button" className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Button asChild size="lg" className="group">
              <Link href={`/${locale}/register`}>
                {t("getStarted")}
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link href={`/${locale}/login`}>{t("signIn")}</Link>
            </Button>
          </Reveal>
        </RevealGroup>
      </section>

      {/* ============================== FOOTER ============================== */}
      <Footer />

      {/* Floating pre-sales chatbot — lazy, never blocks first paint. */}
      <LandingChatbot />
    </div>
    </SmoothScroll>
  );
}

function CycleTab({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full px-4 py-1.5 text-sm font-medium transition-all",
        active
          ? "bg-background text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function PlanCard({
  plan,
  cycle,
  money,
  busy,
  onChoose,
}: {
  plan: PlanOut;
  cycle: BillingCycle;
  money: (n: number) => string;
  busy: boolean;
  onChoose: () => void;
}) {
  const t = useTranslations("pricing");
  const price = cycle === "yearly" ? plan.yearly_eur_per_user : plan.monthly_eur;
  const isFree = plan.id === "free";

  // Plan tagline/features are localized in messages (pricing.plans.<id>); the
  // /plans API only returns English. Use the translation, falling back to the
  // API value if a key is ever missing (e.g. a new plan id not yet translated).
  const taglineKey = `plans.${plan.id}.tagline`;
  const featuresKey = `plans.${plan.id}.features`;
  const tagline = t.has(taglineKey) ? t(taglineKey) : plan.tagline;
  const features = (t.has(featuresKey) ? t.raw(featuresKey) : plan.features) as string[];

  return (
    <div
      className={cn(
        "group relative flex h-full flex-col overflow-hidden rounded-2xl border bg-card p-7 transition-all",
        plan.highlighted
          ? "border-primary/40 shadow-2xl shadow-primary/10 ring-1 ring-primary/20 lg:-translate-y-2"
          : "hover:-translate-y-1 hover:border-primary/30 hover:shadow-lg",
      )}
    >
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-b",
          PLAN_GRADIENT[plan.id],
        )}
      />

      {plan.highlighted && (
        <div className="absolute right-4 top-4 rounded-full bg-gradient-to-r from-primary to-violet-500 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary-foreground shadow-md">
          {t("mostPopular")}
        </div>
      )}

      <div className="relative flex flex-1 flex-col">
        <div className="text-sm font-semibold text-foreground">{plan.name}</div>
        <p className="mt-1 text-sm text-muted-foreground">{tagline}</p>

        <div className="mt-6 flex items-baseline gap-1">
          <span className="text-5xl font-semibold tracking-tight">
            {isFree ? t("free") : money(price)}
          </span>
          {!isFree && (
            <span className="text-sm text-muted-foreground">{t("perUserPerMonth")}</span>
          )}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {isFree
            ? t("freeCtaSubtext")
            : cycle === "yearly"
              ? t("billedYearly", { total: money(plan.yearly_total_eur) })
              : t("billedMonthly")}
        </p>

        {plan.trial_days > 0 && (
          <div className="mt-3 inline-flex w-fit items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-300">
            <Zap className="h-3 w-3" /> {t("trialBadge", { days: plan.trial_days })}
          </div>
        )}

        <Button
          type="button"
          onClick={onChoose}
          disabled={busy}
          className="mt-6 w-full"
          variant={plan.highlighted ? "default" : "outline"}
          size="lg"
        >
          {busy ? t("redirecting") : isFree ? t("startFree") : t("choose")}
          {!busy && <ArrowRight className="h-4 w-4" />}
        </Button>

        <ul className="mt-7 space-y-2.5 text-sm">
          {features.map((f, i) => {
            const Icon = FEATURE_ICONS[plan.id]?.[i] ?? Check;
            return (
              <li key={f} className="flex items-start gap-2">
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <span>{f}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

function PlanSkeleton({ count }: { count: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="h-[520px] animate-pulse rounded-2xl border bg-card/50"
          style={{ animationDelay: `${i * 80}ms` }}
        />
      ))}
    </>
  );
}

type Cell = boolean | string;
type Row = { label: string; cells: Cell[] };

function buildMatrix(
  plans: PlanOut[],
  t: (key: string, values?: Record<string, string | number>) => string,
  locale: string,
): Row[] {
  return [
    {
      label: t("matrix.users"),
      cells: plans.map((p) =>
        // next-intl validates ICU vars eagerly, so the `{n}` placeholder must
        // be passed through `t`'s values arg — a post-hoc `.replace()` throws a
        // FORMATTING_ERROR and leaves the raw "{n}" in the cell.
        p.seat_limit ? t("matrix.upTo", { n: p.seat_limit }) : t("matrix.unlimited"),
      ),
    },
    { label: t("matrix.coreCrm"), cells: plans.map(() => true) },
    {
      label: t("matrix.aiCredits"),
      cells: plans.map((p) =>
        p.ai_credits == null
          ? t("matrix.unlimited")
          : new Intl.NumberFormat(locale).format(p.ai_credits),
      ),
    },
    { label: t("matrix.reports"), cells: plans.map((p) => p.id !== "free") },
    { label: t("matrix.contracts"), cells: plans.map((p) => p.id === "business" || p.id === "premium") },
    { label: t("matrix.audit"), cells: plans.map((p) => p.id === "business" || p.id === "premium") },
    { label: t("matrix.automations"), cells: plans.map((p) => p.id === "business" || p.id === "premium") },
    { label: t("matrix.api"), cells: plans.map((p) => p.id === "premium") },
    {
      label: t("matrix.support"),
      cells: plans.map((p) =>
        p.id === "premium"
          ? t("matrix.supportDedicated")
          : p.id === "free"
            ? t("matrix.supportEmail")
            : t("matrix.supportPriority"),
      ),
    },
  ];
}
