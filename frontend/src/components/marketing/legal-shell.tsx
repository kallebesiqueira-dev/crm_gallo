"use client";

import { useTranslations } from "next-intl";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useLocale } from "next-intl";
import { FuturisticBackground } from "@/components/marketing/futuristic-background";
import { Footer } from "@/components/marketing/footer";
import { Logo } from "@/components/logo";
import { LanguageSwitcher } from "@/components/language-switcher";

/**
 * Shared shell for marketing-surface legal pages (Terms, Cookies, etc.).
 *
 * Renders the same dark/futuristic chrome as the landing — single page-wide
 * mesh, sticky header with the brand, the new partners-style footer at the
 * bottom — wrapped around a centred max-w-3xl reading column tuned for long
 * legal copy. The `dark` class on the root forces the dark palette regardless
 * of the user's theme preference, matching the rest of the marketing surface.
 *
 * Pages pass:
 *   - `title`  — h1 above the body
 *   - `lastUpdated` — ISO date string, rendered with the localised label
 *   - `children` — the sections themselves (use <LegalSection>)
 */
export function LegalShell({
  title,
  lastUpdated,
  children,
}: {
  title: string;
  lastUpdated: string;
  children: React.ReactNode;
}) {
  const tApp = useTranslations("app");
  const tLegal = useTranslations("legal");
  const locale = useLocale();

  return (
    <div className="dark relative min-h-dvh text-foreground">
      <FuturisticBackground />

      {/* Sticky header — same shape as the landing's, minus the long nav */}
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#040509]/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
          <Logo href="/" size="md" label={tApp("name")} />
          <div className="flex items-center gap-3">
            <Link
              href={`/${locale}`}
              className="hidden items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground sm:inline-flex"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              {tLegal("backToHome")}
            </Link>
            <LanguageSwitcher />
          </div>
        </div>
      </header>

      {/* Reading column */}
      <main className="relative mx-auto max-w-3xl px-6 py-16 sm:py-24">
        {/* Title block — soft halo behind the headline so it picks up the
            futuristic glow without overwhelming the reading flow. */}
        <div className="relative">
          <span
            aria-hidden
            className="pointer-events-none absolute -inset-x-6 -inset-y-4 -z-10 rounded-[40px] bg-gradient-to-br from-blue-500/10 via-violet-500/8 to-fuchsia-500/10 blur-3xl"
          />
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
            {tLegal("eyebrow")}
          </p>
          <h1 className="mt-3 text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
            {title}
          </h1>
          <p className="mt-4 text-sm text-muted-foreground">
            {tLegal("lastUpdated")}:{" "}
            <time dateTime={lastUpdated} className="text-foreground/80">
              {new Intl.DateTimeFormat(locale, {
                year: "numeric",
                month: "long",
                day: "numeric",
              }).format(new Date(lastUpdated))}
            </time>
          </p>
          <p className="mt-3 text-xs text-muted-foreground/70">
            {tLegal("templateNotice")}
          </p>
        </div>

        {/* Content sections */}
        <div className="mt-12 space-y-10">{children}</div>

        {/* Back-to-home affordance at the bottom of the long read */}
        <div className="mt-16 border-t border-white/5 pt-8">
          <Link
            href={`/${locale}`}
            className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            {tLegal("backToHome")}
          </Link>
        </div>
      </main>

      <Footer />
    </div>
  );
}

/**
 * Single labelled section inside a <LegalShell>. Keeps consistent
 * heading scale, spacing, and prose styling across pages.
 */
export function LegalSection({
  number,
  title,
  children,
}: {
  number: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="scroll-mt-24" id={`section-${number}`}>
      <h2 className="flex items-baseline gap-3 text-xl font-semibold tracking-tight sm:text-2xl">
        <span className="font-mono text-sm font-medium text-primary">
          {number.toString().padStart(2, "0")}
        </span>
        {title}
      </h2>
      <div className="mt-4 space-y-3 text-sm leading-relaxed text-muted-foreground sm:text-base">
        {children}
      </div>
    </section>
  );
}
