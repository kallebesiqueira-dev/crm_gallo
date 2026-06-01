"use client";

import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

/**
 * Dual-direction logo marquee. Top row scrolls right→left, bottom row
 * left→right. Each track contains a duplicated set of logos so the
 * `translateX(-50%)` loop is perfectly seamless. Edge mask fades the
 * logos in and out so they don't pop on the viewport boundary.
 *
 * No real customer names — these are stylized text marks. Swap with
 * real customer SVGs as sales lands logo permissions.
 */

interface LogoMark {
  name: string;
  className: string;
}

const TOP_LOGOS: LogoMark[] = [
  { name: "Northwind", className: "font-serif tracking-tight" },
  { name: "ACME ⚡", className: "font-mono tracking-tighter" },
  { name: "GLOBEX", className: "font-sans font-black tracking-widest" },
  { name: "INITECH", className: "font-mono tracking-wider" },
  { name: "Vandelay", className: "font-serif italic" },
  { name: "Wayne ◆", className: "font-sans font-bold tracking-tight" },
  { name: "STARK", className: "font-mono font-bold tracking-[0.2em]" },
  { name: "Soylent", className: "font-serif tracking-wide" },
];

const BOTTOM_LOGOS: LogoMark[] = [
  { name: "Hooli", className: "font-sans font-semibold tracking-tight" },
  { name: "Pied Piper △", className: "font-serif tracking-wide" },
  { name: "DUNDER", className: "font-mono tracking-[0.18em]" },
  { name: "WEYLAND ✶", className: "font-sans font-black tracking-widest" },
  { name: "Aperture", className: "font-serif italic tracking-tight" },
  { name: "Tyrell", className: "font-mono italic" },
  { name: "CYBERDYNE", className: "font-sans font-bold tracking-[0.16em]" },
  { name: "Massive Dynamic", className: "font-sans tracking-tight" },
];

export function LogosBand() {
  const t = useTranslations("marketing");
  return (
    <section>
      <div className="mx-auto max-w-7xl px-6 py-14">
        <p className="text-center text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          {t("logosTitle")}
        </p>

        <div
          className="mt-10 space-y-6"
          // Edge fade — logos dissolve into the section background instead of
          // popping at the edges. Standard Stripe / Linear pattern.
          style={{
            WebkitMaskImage:
              "linear-gradient(to right, transparent 0, black 8%, black 92%, transparent 100%)",
            maskImage:
              "linear-gradient(to right, transparent 0, black 8%, black 92%, transparent 100%)",
          }}
        >
          <MarqueeRow direction="left" logos={TOP_LOGOS} />
          <MarqueeRow direction="right" logos={BOTTOM_LOGOS} />
        </div>
      </div>
    </section>
  );
}

function MarqueeRow({
  direction,
  logos,
}: {
  direction: "left" | "right";
  logos: LogoMark[];
}) {
  // The track must contain the logos twice so a translateX of -50% (or 0)
  // lands exactly on a duplicate, giving a seamless infinite loop.
  // The whole row is decorative — the section heading above announces the
  // intent. Screen readers get nothing useful from animating placeholder
  // logos, so we hide the entire marquee from them.
  return (
    <div
      className="group relative overflow-hidden"
      aria-hidden="true"
      role="presentation"
    >
      <div
        className={cn(
          "flex w-max items-center gap-12 will-change-transform",
          direction === "left" ? "animate-marquee-left" : "animate-marquee-right",
          // Pause on hover — small UX touch users notice subconsciously.
          "group-hover:[animation-play-state:paused]",
        )}
      >
        {[...logos, ...logos].map((logo, i) => (
          <div
            key={`${logo.name}-${i}`}
            className={cn(
              "shrink-0 px-2 text-sm text-foreground/60 transition-colors hover:text-foreground",
              logo.className,
            )}
          >
            {logo.name}
          </div>
        ))}
      </div>
    </div>
  );
}
