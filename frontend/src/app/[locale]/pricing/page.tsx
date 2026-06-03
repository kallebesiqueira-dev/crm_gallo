"use client";

import { Suspense, useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import {
  ArrowRight,
  ArrowUpRight,
  Award,
  Check,
  ShieldCheck,
  Sparkles,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { LanguageSwitcher } from "@/components/language-switcher";
import { DashboardCarousel } from "@/components/marketing/dashboard-carousel";
import { LogosBand } from "@/components/marketing/logos-band";
import { StatsCounter } from "@/components/marketing/stats-counter";
import { FeatureSections } from "@/components/marketing/feature-section";
import { Testimonials } from "@/components/marketing/testimonials";
import { AboutSection } from "@/components/marketing/about-section";
import { ValuesSection } from "@/components/marketing/values-section";
import { ManifestoSection } from "@/components/marketing/manifesto-section";
import { ComparisonSection } from "@/components/marketing/comparison-section";
import { Reveal, RevealGroup } from "@/components/marketing/reveal";
import { FuturisticBackground } from "@/components/marketing/futuristic-background";
import { Footer } from "@/components/marketing/footer";
import { Logo } from "@/components/logo";
import { SmoothScroll } from "@/components/marketing/smooth-scroll";
import { SearchParamWatcher } from "@/components/search-param-watcher";
import { api, type PlanOut, type PlanId, type BillingCycle } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

const PLAN_GRADIENT: Record<PlanId, string> = {
  free: "from-slate-500/10 to-slate-500/0",
  standard: "from-primary/20 to-blue-500/0",
  premium: "from-amber-500/20 via-fuchsia-500/10 to-pink-500/0",
};

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
    api.plans().then(setPlans).catch(() => setPlans([]));
  }, []);

  // `?stripe=cancel` comes back from an abandoned Checkout — surface a
  // gentle banner. The flag is read by <SearchParamWatcher> below so
  // useSearchParams() stays inside its own Suspense boundary.
  useEffect(() => {
    if (stripeFlag === "cancel") {
      setBanner(t("checkoutCanceled"));
    }
  }, [stripeFlag, t]);

  const moneyFmt = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });

  async function handleChoose(plan: PlanOut) {
    if (!plan.requires_payment) {
      router.push(`/${locale}/register?plan=${plan.id}`);
      return;
    }
    const token = getToken();
    if (!token) {
      router.push(`/${locale}/register?plan=${plan.id}&cycle=${cycle}`);
      return;
    }
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
  }

  return (
    <SmoothScroll>
    {/* `dark` on the root forces the landing into dark mode regardless of
        the user's theme preference — the rest of the app (auth, dashboard,
        etc.) still respects the toggle. <FuturisticBackground> is fixed to
        the viewport at z-0 and provides the actual base colour; every other
        page surface stacks above via `relative z-10` so it can't get hidden
        behind the mesh. */}
    <div className="dark relative min-h-screen text-foreground">
      <Suspense fallback={null}>
        <SearchParamWatcher name="stripe" onValue={setStripeFlag} />
      </Suspense>
      <FuturisticBackground />
      {/* Sticky header */}
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#040509]/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
          <Logo href="/" size="md" label={tApp("name")} />
          <nav className="hidden items-center gap-6 text-sm md:flex">
            <a href="#manifesto" className="text-muted-foreground hover:text-foreground">
              {tMarketing("navManifesto")}
            </a>
            <a href="#about" className="text-muted-foreground hover:text-foreground">
              {tMarketing("navAbout")}
            </a>
            <a href="#values" className="text-muted-foreground hover:text-foreground">
              {tMarketing("navValues")}
            </a>
            <a href="#features" className="text-muted-foreground hover:text-foreground">
              {tMarketing("navFeatures")}
            </a>
            <a href="#pricing" className="text-muted-foreground hover:text-foreground">
              {tMarketing("navPricing")}
            </a>
            <a href="#faq" className="text-muted-foreground hover:text-foreground">
              {tMarketing("navFaq")}
            </a>
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
            {/* Dashed outer ring */}
            <svg
              aria-hidden
              viewBox="0 0 512 512"
              className="absolute -inset-4 h-[calc(100%+2rem)] w-[calc(100%+2rem)] text-foreground/25"
              fill="none"
            >
              <circle cx="256" cy="256" r="252" stroke="currentColor" strokeWidth="1.5" strokeDasharray="6 9" />
            </svg>

            {/* Inner aspect-square so the colored blob and image scale
                consistently across breakpoints without manual hxw values. */}
            <div className="relative aspect-square w-full">
              {/* Colored gradient blob — orange→rose→pink to echo the reference */}
              <div className="absolute inset-0 rounded-full bg-gradient-to-br from-orange-500 via-rose-500 to-pink-500 shadow-2xl shadow-rose-500/30 dark:shadow-rose-500/40" />
              {/* Inner glossy highlight */}
              <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-transparent via-white/10 to-white/25 mix-blend-overlay" />

              {/* The gallo image, clipped to the circle. object-cover so the
                  bird's silhouette fills the disc nicely. */}
              <div className="absolute inset-0 overflow-hidden rounded-full ring-1 ring-white/10">
                <Image
                  src="/gallo_img.png"
                  alt=""
                  fill
                  priority
                  sizes="(min-width: 1024px) 480px, 90vw"
                  className="object-cover object-center scale-105"
                />
              </div>

              {/* Floating "award" card — overlaps bottom-left of the image,
                  same idea as the reference's "The Best Design Awards" card. */}
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

              {/* Floating "stat" chip — top-right, gives the visual extra
                  density without competing with the headline. */}
              <div className="absolute -right-2 top-6 z-10 hidden items-center gap-2 rounded-full border bg-background/95 px-3 py-1.5 text-[11px] font-medium shadow-xl backdrop-blur-xl sm:flex">
                <Sparkles className="h-3 w-3 text-violet-500" />
                <span>{t("heroBadge")}</span>
              </div>
            </div>
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
          <DashboardCarousel />
        </Reveal>
      </section>

      {/* ============================== LOGOS ============================== */}
      <LogosBand />

      {/* ============================== ABOUT / CHI SIAMO ============================== */}
      <AboutSection />

      {/* ============================== STATS ============================== */}
      <div data-reveal="fade-up">
        <StatsCounter />
      </div>

      {/* ============================== VALUES / I NOSTRI VALORI ============================== */}
      <ValuesSection />

      {/* ============================== FEATURES ============================== */}
      <div id="features">
        <FeatureSections />
      </div>

      {/* ============================== TESTIMONIALS ============================== */}
      <Testimonials />

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
            className="mt-12 grid gap-6 lg:grid-cols-3"
            stagger={0.12}
            delayChildren={0.15}
          >
            {plans === null && <PlanSkeleton count={3} />}
            {plans?.map((plan) => (
              <Reveal key={plan.id} variant="card">
                <PlanCard
                  plan={plan}
                  cycle={cycle}
                  moneyFmt={moneyFmt}
                  busy={busyPlan === plan.id}
                  onChoose={() => handleChoose(plan)}
                />
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
              <table className="w-full text-sm">
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
                  {buildMatrix(plans, t).map((row) => (
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
                            <Check className="mx-auto h-4 w-4 text-emerald-500" />
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
  moneyFmt,
  busy,
  onChoose,
}: {
  plan: PlanOut;
  cycle: BillingCycle;
  moneyFmt: Intl.NumberFormat;
  busy: boolean;
  onChoose: () => void;
}) {
  const t = useTranslations("pricing");
  const price = cycle === "yearly" ? plan.yearly_eur_per_user : plan.monthly_eur;
  const isFree = plan.id === "free";

  return (
    <div
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-2xl border bg-card p-7 transition-all",
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
        <p className="mt-1 text-sm text-muted-foreground">{plan.tagline}</p>

        <div className="mt-6 flex items-baseline gap-1">
          <span className="text-5xl font-semibold tracking-tight">
            {isFree ? t("free") : moneyFmt.format(price)}
          </span>
          {!isFree && (
            <span className="text-sm text-muted-foreground">{t("perUserPerMonth")}</span>
          )}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {isFree
            ? t("freeCtaSubtext")
            : cycle === "yearly"
              ? t("billedYearly")
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
          {plan.features.map((f) => (
            <li key={f} className="flex items-start gap-2">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
              <span>{f}</span>
            </li>
          ))}
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

function buildMatrix(plans: PlanOut[], t: (k: string) => string): Row[] {
  return [
    {
      label: t("matrix.users"),
      cells: plans.map((p) =>
        p.seat_limit ? t("matrix.upTo").replace("{n}", String(p.seat_limit)) : t("matrix.unlimited"),
      ),
    },
    { label: t("matrix.coreCrm"), cells: plans.map(() => true) },
    { label: t("matrix.aiScoringPro"), cells: plans.map((p) => p.id !== "free") },
    { label: t("matrix.aiAssistant"), cells: plans.map((p) => p.id !== "free") },
    { label: t("matrix.reports"), cells: plans.map((p) => p.id !== "free") },
    { label: t("matrix.automations"), cells: plans.map((p) => p.id === "premium") },
    { label: t("matrix.integrations"), cells: plans.map((p) => p.id === "premium") },
    { label: t("matrix.rag"), cells: plans.map((p) => p.id === "premium") },
    { label: t("matrix.api"), cells: plans.map((p) => p.id === "premium") },
    {
      label: t("matrix.support"),
      cells: plans.map((p) =>
        p.id === "premium" ? t("matrix.supportDedicated") : p.id === "standard" ? t("matrix.supportPriority") : t("matrix.supportEmail"),
      ),
    },
  ];
}
