"use client";

import { useTranslations } from "next-intl";
import { Infinity as InfinityIcon, Plug, Workflow } from "lucide-react";
import { Reveal, RevealGroup } from "@/components/marketing/reveal";

const PILLARS: { id: "connect" | "automate" | "create"; icon: typeof Plug }[] = [
  { id: "connect", icon: Plug },
  { id: "automate", icon: Workflow },
  { id: "create", icon: InfinityIcon },
];

export function ManifestoSection() {
  const t = useTranslations("marketing");

  return (
    <section id="manifesto" className="relative">
      {/* No local ambient overlays here — the page-wide FuturisticBackground
          is the only source of light/colour, so the manifesto reads as one
          continuous flow with the rest of the page, no rectangular "box"
          showing where the section starts. The title still has its own
          decorative halo (inside the Reveal below), kept local to the
          glyphs so it never paints a section boundary. */}
      <RevealGroup className="relative mx-auto max-w-5xl px-6 py-28 text-center">
        <Reveal
          variant="soft"
          className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-background/60 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-primary backdrop-blur-xl"
        >
          <InfinityIcon className="h-3 w-3" />
          {t("manifesto.eyebrow")}
        </Reveal>

        <Reveal
          variant="text"
          className="mx-auto mt-8 max-w-3xl text-lg font-medium text-foreground/85 sm:text-xl"
        >
          {t("manifesto.line1")}
        </Reveal>

        {/* Title with animated glow halo behind it */}
        <Reveal variant="title" className="relative mt-4">
          <span
            aria-hidden
            className="pointer-events-none absolute -inset-x-10 -inset-y-8 -z-10 rounded-[60px] bg-gradient-to-br from-blue-500/20 via-violet-500/15 to-fuchsia-500/20 blur-3xl animate-pulse-slow"
          />
          <h2 className="bg-gradient-to-br from-blue-500 via-violet-500 to-fuchsia-500 bg-clip-text text-4xl font-semibold leading-[1.1] tracking-tight text-transparent drop-shadow-[0_3px_18px_rgba(99,102,241,0.25)] sm:text-6xl">
            {t("manifesto.line2")}
          </h2>
        </Reveal>

        <Reveal
          variant="text"
          className="mx-auto mt-6 max-w-2xl text-base text-muted-foreground sm:text-lg"
        >
          {t("manifesto.line3")}
        </Reveal>

        <RevealGroup
          className="mx-auto mt-14 grid max-w-3xl gap-4 sm:grid-cols-3"
          stagger={0.12}
          delayChildren={0.15}
        >
          {PILLARS.map((pillar) => {
            const Icon = pillar.icon;
            return (
              <Reveal
                key={pillar.id}
                variant="card"
                className="group relative overflow-hidden rounded-2xl border border-white/10 bg-card/60 p-5 text-left backdrop-blur-xl transition-all duration-[250ms] hover:-translate-y-1.5 hover:scale-[1.03] hover:border-primary/40 hover:shadow-2xl hover:shadow-primary/10"
              >
                <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-primary to-violet-500 text-primary-foreground shadow-lg shadow-primary/20">
                  <Icon className="h-4 w-4" />
                </div>
                <div className="mt-3 text-sm font-semibold">
                  {t(`manifesto.pillars.${pillar.id}.title`)}
                </div>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {t(`manifesto.pillars.${pillar.id}.body`)}
                </p>
              </Reveal>
            );
          })}
        </RevealGroup>
      </RevealGroup>
    </section>
  );
}
