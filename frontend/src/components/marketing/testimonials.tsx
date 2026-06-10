"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Reveal, RevealGroup } from "@/components/marketing/reveal";
import { cn } from "@/lib/utils";

/**
 * Testimonials carousel — 12 quotes, gender-matched photos, responsive
 * visible count (1 mobile / 2 tablet / 3 desktop), arrow + dot controls.
 *
 * The card list is fixed; the visible window slides by translating the
 * track. We advance by one card per click (Embla-style) and the dots
 * map to every reachable starting index, so users always know how far
 * they are through the set.
 */

interface Quote {
  id: number;
  initials: string;
  accent: string;
  photo: string;
}

// Photos: men/* and women/* seeds from randomuser.me, picked to spread
// across hair colour / skin tone / age so the row feels human rather
// than templated.
const QUOTES: Quote[] = [
  { id: 1,  initials: "AM", accent: "from-blue-500 to-violet-500",    photo: "https://randomuser.me/api/portraits/women/44.jpg" },
  { id: 2,  initials: "LP", accent: "from-emerald-500 to-teal-500",   photo: "https://randomuser.me/api/portraits/women/76.jpg" },
  { id: 3,  initials: "JR", accent: "from-amber-500 to-rose-500",     photo: "https://randomuser.me/api/portraits/women/65.jpg" },
  { id: 4,  initials: "MB", accent: "from-violet-500 to-fuchsia-500", photo: "https://randomuser.me/api/portraits/men/32.jpg" },
  { id: 5,  initials: "SL", accent: "from-pink-500 to-rose-500",      photo: "https://randomuser.me/api/portraits/women/12.jpg" },
  { id: 6,  initials: "HM", accent: "from-cyan-500 to-blue-500",      photo: "https://randomuser.me/api/portraits/men/45.jpg" },
  { id: 7,  initials: "CD", accent: "from-amber-500 to-orange-500",   photo: "https://randomuser.me/api/portraits/women/8.jpg" },
  { id: 8,  initials: "DC", accent: "from-emerald-500 to-cyan-500",   photo: "https://randomuser.me/api/portraits/men/68.jpg" },
  { id: 9,  initials: "AK", accent: "from-fuchsia-500 to-purple-500", photo: "https://randomuser.me/api/portraits/women/33.jpg" },
  { id: 10, initials: "TW", accent: "from-teal-500 to-emerald-500",   photo: "https://randomuser.me/api/portraits/men/22.jpg" },
  { id: 11, initials: "IR", accent: "from-rose-500 to-red-500",       photo: "https://randomuser.me/api/portraits/women/50.jpg" },
  { id: 12, initials: "CM", accent: "from-blue-500 to-indigo-500",    photo: "https://randomuser.me/api/portraits/men/85.jpg" },
];

/** Resolve how many cards fit at the current viewport (1 / 2 / 3). */
function useVisibleCount(): number {
  const [count, setCount] = useState(3);
  useEffect(() => {
    const compute = () => {
      const w = window.innerWidth;
      setCount(w >= 1024 ? 3 : w >= 640 ? 2 : 1);
    };
    compute();
    window.addEventListener("resize", compute);
    return () => window.removeEventListener("resize", compute);
  }, []);
  return count;
}

export function Testimonials() {
  const t = useTranslations("marketing");
  const visible = useVisibleCount();
  const [index, setIndex] = useState(0);
  const maxIndex = Math.max(0, QUOTES.length - visible);

  // Re-clamp when viewport changes so the user never lands on an
  // unreachable index after a resize.
  useEffect(() => {
    if (index > maxIndex) setIndex(maxIndex);
  }, [index, maxIndex]);

  // Looping nav: from the last position, "next" wraps to 0; from 0,
  // "prev" wraps to maxIndex. Feels more discovery-friendly than a
  // dead-stop at the ends.
  const next = useCallback(() => setIndex((i) => (i >= maxIndex ? 0 : i + 1)), [maxIndex]);
  const prev = useCallback(() => setIndex((i) => (i <= 0 ? maxIndex : i - 1)), [maxIndex]);

  return (
    <section>
      <div className="mx-auto max-w-7xl px-6 py-20">
        <RevealGroup className="text-center">
          <Reveal
            variant="soft"
            className="text-xs font-semibold uppercase tracking-[0.18em] text-primary"
          >
            {t("testimonialsEyebrow")}
          </Reveal>
          <Reveal variant="title" className="relative mt-3">
            <span
              aria-hidden
              className="pointer-events-none absolute -inset-x-10 -inset-y-6 -z-10 rounded-[60px] bg-gradient-to-br from-primary/15 via-violet-500/10 to-fuchsia-500/15 blur-3xl"
            />
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              {t("testimonialsTitle")}
            </h2>
          </Reveal>
        </RevealGroup>

        <Reveal standalone variant="base" className="relative mt-12">
          {/* Arrow controls — placed slightly inside the track at md+ so
              they don't clip the viewport edge on tighter screens. */}
          <button
            type="button"
            onClick={prev}
            aria-label="Previous"
            className="absolute left-0 top-1/2 z-10 -translate-y-1/2 grid h-10 w-10 place-items-center rounded-full border border-white/15 bg-card/80 text-foreground shadow-lg backdrop-blur-xl transition-all duration-[200ms] hover:scale-110 hover:border-primary/40 hover:bg-card md:-translate-x-5"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={next}
            aria-label="Next"
            className="absolute right-0 top-1/2 z-10 -translate-y-1/2 grid h-10 w-10 place-items-center rounded-full border border-white/15 bg-card/80 text-foreground shadow-lg backdrop-blur-xl transition-all duration-[200ms] hover:scale-110 hover:border-primary/40 hover:bg-card md:translate-x-5"
          >
            <ChevronRight className="h-4 w-4" />
          </button>

          {/* Sliding track */}
          <div className="overflow-x-clip py-4">
            <motion.div
              className="flex items-stretch"
              animate={{ x: `-${(index * 100) / visible}%` }}
              transition={{ duration: 0.65, ease: [0.16, 1, 0.3, 1] }}
            >
              {QUOTES.map((q) => (
                <div
                  key={q.id}
                  className={cn(
                    "shrink-0 px-3",
                    visible === 1 && "w-full",
                    visible === 2 && "w-1/2",
                    visible === 3 && "w-1/3",
                  )}
                >
                  <TestimonialCard q={q} t={t} />
                </div>
              ))}
            </motion.div>
          </div>

          {/* Dots — one per reachable starting index */}
          <div className="mt-8 flex items-center justify-center gap-2">
            {Array.from({ length: maxIndex + 1 }).map((_, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setIndex(i)}
                aria-label={`Page ${i + 1}`}
                className={cn(
                  "h-1.5 rounded-full transition-all duration-300",
                  i === index ? "w-8 bg-foreground" : "w-1.5 bg-foreground/25 hover:bg-foreground/50",
                )}
              />
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function TestimonialCard({
  q,
  t,
}: {
  q: Quote;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <figure className="group relative flex h-full flex-col rounded-2xl border bg-card p-7 shadow-sm transition-all duration-[250ms] hover:-translate-y-1.5 hover:scale-[1.03] hover:border-primary/40 hover:shadow-2xl hover:shadow-primary/10">
      {/* Decorative quote glyph — gradient text behind the actual blockquote */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -top-2 left-5 select-none bg-gradient-to-br from-primary/40 to-violet-500/30 bg-clip-text font-serif text-[7rem] leading-none text-transparent"
      >
        &ldquo;
      </span>

      <blockquote className="relative flex-1 pt-6 text-sm leading-relaxed">
        {t(`testimonial.${q.id}.quote`)}
      </blockquote>

      <figcaption className="relative mt-6 flex items-center gap-3 border-t pt-4">
        <Avatar
          photo={q.photo}
          initials={q.initials}
          accent={q.accent}
          alt={t(`testimonial.${q.id}.author`)}
        />
        <div>
          <div className="text-sm font-medium">{t(`testimonial.${q.id}.author`)}</div>
          <div className="text-xs text-muted-foreground">{t(`testimonial.${q.id}.role`)}</div>
        </div>
      </figcaption>
    </figure>
  );
}

/**
 * Photo avatar with graceful initials fallback. We hit randomuser.me at
 * runtime (stable stock portraits, no key needed). If the request fails —
 * offline preview, ad-blocker, etc. — the gradient initials chip takes
 * over so the card never looks broken.
 */
function Avatar({
  photo,
  initials,
  accent,
  alt,
}: {
  photo: string;
  initials: string;
  accent: string;
  alt: string;
}) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div
        className={`grid h-10 w-10 place-items-center rounded-full bg-gradient-to-br text-sm font-semibold text-white ${accent}`}
      >
        {initials}
      </div>
    );
  }

  return (
    <img
      src={photo}
      alt={alt}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="h-10 w-10 shrink-0 rounded-full object-cover ring-2 ring-background shadow-md"
    />
  );
}
