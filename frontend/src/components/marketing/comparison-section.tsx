"use client";

import Image from "next/image";
import { useTranslations } from "next-intl";
import {
  AlertTriangle,
  BarChart3,
  Sparkles,
  TrendingUp,
  Workflow,
  Zap,
} from "lucide-react";
import { Reveal, RevealGroup } from "@/components/marketing/reveal";
import { cn } from "@/lib/utils";

/**
 * "Why CRM Gallo" comparison band — three-column lockup with the Gallo
 * mascot in the centre, an "other CRMs" card on the left (deliberately
 * muted), and a "CRM Gallo" card on the right (full colour, gradient
 * accents). Inspired by Datacrazy's split-comparison hero, adapted to
 * our dark, futuristic surface.
 *
 * The image is `public/gallino.png` (anthropomorphic rooster). It floats
 * above a pulsing radial glow and a handful of orbiting "data particles"
 * that pick up the brand palette — pure decoration, no canvas/3D.
 *
 * All text comes from the `marketing.comparison` namespace so the section
 * is fully translated alongside the rest of the page.
 */

interface ComparisonItem {
  icon: typeof Zap;
  titleKey: string;
  bodyKey: string;
}

const LEFT_ITEMS: ComparisonItem[] = [
  { icon: Zap,        titleKey: "left.items.automation.title", bodyKey: "left.items.automation.body" },
  { icon: TrendingUp, titleKey: "left.items.growth.title",     bodyKey: "left.items.growth.body" },
];

const RIGHT_ITEMS: ComparisonItem[] = [
  { icon: Sparkles,   titleKey: "right.items.automation.title", bodyKey: "right.items.automation.body" },
  { icon: BarChart3,  titleKey: "right.items.growth.title",     bodyKey: "right.items.growth.body" },
];

// Hand-picked particle positions so the glow ring around the gallino
// always looks balanced. Each tuple is [topPct, leftPct, sizePx, delayS].
const PARTICLES: Array<[number, number, number, number, string]> = [
  [10, 12, 4, 0,   "bg-blue-400/70"],
  [22, 88, 3, 1.2, "bg-violet-400/70"],
  [55, 6,  3, 2.4, "bg-cyan-400/70"],
  [70, 92, 4, 0.6, "bg-fuchsia-400/70"],
  [88, 28, 3, 1.8, "bg-amber-400/70"],
  [40, 95, 2, 3.0, "bg-emerald-400/70"],
];

export function ComparisonSection() {
  const t = useTranslations("marketing.comparison");

  return (
    <section id="why-gallo" className="relative overflow-hidden">
      <div className="mx-auto max-w-7xl px-6 py-24 sm:py-28">
        {/* Header */}
        <RevealGroup className="mx-auto max-w-4xl text-center">
          <Reveal
            variant="soft"
            className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-card/60 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-primary backdrop-blur-xl"
          >
            <Sparkles className="h-3 w-3" />
            {t("eyebrow")}
          </Reveal>

          {/* Title with a single coloured accent on the closing line */}
          <Reveal variant="title" className="relative mt-5">
            <span
              aria-hidden
              className="pointer-events-none absolute -inset-x-10 -inset-y-6 -z-10 rounded-[60px] bg-gradient-to-br from-rose-500/15 via-orange-500/10 to-amber-500/15 blur-3xl"
            />
            <h2 className="text-4xl font-bold leading-[1.05] tracking-tight text-foreground sm:text-5xl lg:text-6xl">
              {t("titlePre")}{" "}
              <span className="bg-gradient-to-br from-rose-500 via-rose-400 to-orange-400 bg-clip-text text-transparent">
                {t("titleAccent")}
              </span>
            </h2>
          </Reveal>

          <Reveal
            variant="text"
            className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-muted-foreground sm:text-lg"
          >
            {t("subtitle")}
          </Reveal>
        </RevealGroup>

        {/* 3-column lockup. On mobile the gallino comes first (the hook),
            then the two cards stack underneath. On lg the layout is
            symmetric: muted-card / gallino / vibrant-card. */}
        <div className="mt-16 grid items-center gap-8 lg:grid-cols-12 lg:gap-6">
          {/* LEFT — Other CRMs (muted, desaturated) */}
          <Reveal standalone variant="fade-right" className="order-2 lg:order-1 lg:col-span-4">
            <ComparisonCard
              tone="muted"
              headerPre={t("left.headerPre")}
              headerAccent={t("left.headerAccent")}
              subtitle={t("left.subtitle")}
              items={LEFT_ITEMS.map((i) => ({ ...i, t }))}
              accentIcon={AlertTriangle}
            />
          </Reveal>

          {/* CENTER — Gallino mascot */}
          <Reveal standalone variant="scaleIn" className="order-1 lg:order-2 lg:col-span-4">
            <div className="group relative mx-auto aspect-square w-full max-w-[440px]">
              {/* Pulsing radial glow behind the mascot */}
              <div
                aria-hidden
                className="absolute inset-4 -z-10 rounded-full bg-gradient-to-br from-blue-500/40 via-violet-500/30 to-fuchsia-500/40 blur-3xl animate-pulse-slow"
              />
              {/* Inner halo ring (decorative) */}
              <div
                aria-hidden
                className="absolute inset-8 -z-10 rounded-full bg-gradient-to-tr from-cyan-400/20 via-blue-500/10 to-transparent blur-2xl animate-pulse-slower"
              />

              {/* Orbiting particles — small floating dots */}
              {PARTICLES.map(([top, left, size, delay, color], i) => (
                <span
                  key={i}
                  aria-hidden
                  className={cn("absolute rounded-full blur-[1px] animate-float", color)}
                  style={{
                    top: `${top}%`,
                    left: `${left}%`,
                    width: `${size * 4}px`,
                    height: `${size * 4}px`,
                    animationDelay: `${delay}s`,
                  }}
                />
              ))}

              {/* The mascot — bubble-inflates on hover to invite interaction */}
              <Image
                src="/gallino.png"
                alt="CRM Gallo mascot"
                fill
                priority
                sizes="(min-width: 1024px) 440px, 80vw"
                className="object-contain drop-shadow-[0_20px_60px_rgba(99,102,241,0.45)] transition-transform duration-[700ms] ease-[cubic-bezier(0.34,1.56,0.64,1)] group-hover:scale-[1.04]"
              />
            </div>
          </Reveal>

          {/* RIGHT — CRM Gallo (vibrant, gradient accents) */}
          <Reveal standalone variant="fade-left" className="order-3 lg:col-span-4">
            <ComparisonCard
              tone="primary"
              headerPre={t("right.headerPre")}
              headerAccent={t("right.headerAccent")}
              subtitle={t("right.subtitle")}
              items={RIGHT_ITEMS.map((i) => ({ ...i, t }))}
              accentIcon={Workflow}
            />
          </Reveal>
        </div>
      </div>
    </section>
  );
}

interface CardItemRender extends ComparisonItem {
  t: ReturnType<typeof useTranslations>;
}

function ComparisonCard({
  tone,
  headerPre,
  headerAccent,
  subtitle,
  items,
  accentIcon: AccentIcon,
}: {
  tone: "muted" | "primary";
  headerPre: string;
  headerAccent: string;
  subtitle: string;
  items: CardItemRender[];
  accentIcon: typeof Zap;
}) {
  return (
    <article
      className={cn(
        "group relative h-full overflow-hidden rounded-2xl border p-6 backdrop-blur-xl transition-all duration-[250ms]",
        "hover:-translate-y-1.5 hover:scale-[1.02]",
        tone === "muted"
          ? "border-white/5 bg-white/[0.02] hover:border-white/15"
          : "border-primary/30 bg-card/60 shadow-2xl shadow-primary/15 hover:border-primary/50 hover:shadow-primary/25",
      )}
    >
      {/* Top-right tone icon — orientates the eye quickly */}
      <div
        aria-hidden
        className={cn(
          "absolute -right-2 -top-2 grid h-12 w-12 place-items-center rounded-bl-2xl rounded-tr-2xl",
          tone === "muted"
            ? "bg-rose-500/10 text-rose-400/60"
            : "bg-gradient-to-br from-primary to-violet-500 text-white shadow-lg shadow-primary/30",
        )}
      >
        <AccentIcon className="h-5 w-5" />
      </div>

      {/* Header */}
      <h3 className="pr-10 text-2xl font-bold tracking-tight sm:text-3xl">
        <span className={tone === "muted" ? "text-foreground/70" : "text-foreground"}>
          {headerPre}{" "}
        </span>
        <span
          className={cn(
            tone === "muted"
              ? "text-rose-500"
              : "bg-gradient-to-br from-blue-500 via-violet-500 to-fuchsia-500 bg-clip-text text-transparent",
          )}
        >
          {headerAccent}
        </span>
      </h3>
      <p className="mt-1.5 text-xs text-muted-foreground">{subtitle}</p>

      {/* Items */}
      <div className="mt-6 space-y-3">
        {items.map((item, i) => {
          const Icon = item.icon;
          return (
            <div
              key={i}
              className={cn(
                "flex items-start gap-3 rounded-xl border p-3 transition-colors",
                tone === "muted"
                  ? "border-white/5 bg-black/20"
                  : "border-white/10 bg-black/30 hover:border-primary/30",
              )}
            >
              <div
                className={cn(
                  "grid h-9 w-9 shrink-0 place-items-center rounded-lg",
                  tone === "muted"
                    ? "bg-rose-500/10 text-rose-400/70"
                    : "bg-gradient-to-br from-primary to-violet-500 text-white shadow-lg shadow-primary/20",
                )}
              >
                <Icon className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <div
                  className={cn(
                    "text-sm font-semibold",
                    tone === "muted" ? "text-foreground/80" : "text-foreground",
                  )}
                >
                  {item.t(item.titleKey)}
                </div>
                <div className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                  {item.t(item.bodyKey)}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </article>
  );
}
