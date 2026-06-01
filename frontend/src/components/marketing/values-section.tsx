"use client";

import { useTranslations } from "next-intl";
import {
  Brain,
  Code2,
  Globe2,
  HeartHandshake,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Reveal, RevealGroup } from "@/components/marketing/reveal";

type ValueId = "customer" | "privacy" | "openSource" | "ethicalAi" | "multilingual" | "transparency";

interface ValueDef {
  id: ValueId;
  icon: typeof Sparkles;
  accent: "blue" | "emerald" | "violet" | "amber" | "rose" | "cyan";
}

const VALUES: ValueDef[] = [
  { id: "customer", icon: HeartHandshake, accent: "rose" },
  { id: "privacy", icon: ShieldCheck, accent: "emerald" },
  { id: "openSource", icon: Code2, accent: "blue" },
  { id: "ethicalAi", icon: Brain, accent: "violet" },
  { id: "multilingual", icon: Globe2, accent: "cyan" },
  { id: "transparency", icon: Sparkles, accent: "amber" },
];

const ACCENT: Record<string, { bg: string; icon: string; ring: string }> = {
  blue: { bg: "from-blue-500/15 to-blue-500/0", icon: "from-blue-500 to-blue-600", ring: "ring-blue-500/20" },
  emerald: { bg: "from-emerald-500/15 to-emerald-500/0", icon: "from-emerald-500 to-teal-500", ring: "ring-emerald-500/20" },
  violet: { bg: "from-violet-500/15 to-fuchsia-500/0", icon: "from-violet-500 to-fuchsia-500", ring: "ring-violet-500/20" },
  amber: { bg: "from-amber-500/15 to-amber-500/0", icon: "from-amber-500 to-orange-500", ring: "ring-amber-500/20" },
  rose: { bg: "from-rose-500/15 to-pink-500/0", icon: "from-rose-500 to-pink-500", ring: "ring-rose-500/20" },
  cyan: { bg: "from-cyan-500/15 to-sky-500/0", icon: "from-cyan-500 to-sky-500", ring: "ring-cyan-500/20" },
};

export function ValuesSection() {
  const t = useTranslations("marketing");

  return (
    <section id="values" className="relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/30 to-transparent"
      />

      <div className="mx-auto max-w-6xl px-6 py-24">
        <RevealGroup className="mx-auto max-w-2xl text-center">
          <Reveal
            variant="soft"
            className="text-xs font-semibold uppercase tracking-[0.18em] text-primary"
          >
            {t("values.eyebrow")}
          </Reveal>
          {/* Title with animated glow halo */}
          <Reveal variant="title" className="relative mt-3">
            <span
              aria-hidden
              className="pointer-events-none absolute -inset-x-10 -inset-y-6 -z-10 rounded-[60px] bg-gradient-to-br from-primary/15 via-violet-500/10 to-fuchsia-500/15 blur-3xl animate-pulse-slow"
            />
            <h2 className="text-3xl font-semibold tracking-tight sm:text-5xl">
              {t("values.title")}
            </h2>
          </Reveal>
          <Reveal variant="text" className="mt-4 text-base text-muted-foreground">
            {t("values.subtitle")}
          </Reveal>
        </RevealGroup>

        <RevealGroup
          className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3"
          stagger={0.12}
          delayChildren={0.1}
        >
          {VALUES.map((value) => {
            const Icon = value.icon;
            const accent = ACCENT[value.accent];
            return (
              <Reveal
                key={value.id}
                variant="card"
                className={cn(
                  "group relative overflow-hidden rounded-2xl border bg-card p-7 shadow-sm transition-all duration-[250ms]",
                  "hover:-translate-y-1.5 hover:scale-[1.03] hover:shadow-2xl hover:shadow-primary/10 hover:border-primary/40",
                  "ring-1 ring-transparent hover:ring-1",
                  accent.ring,
                )}
              >
                <div
                  aria-hidden
                  className={cn(
                    "pointer-events-none absolute inset-x-0 top-0 h-32 bg-gradient-to-b transition-opacity",
                    accent.bg,
                  )}
                />

                <div className="relative">
                  <div
                    className={cn(
                      "grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br text-white shadow-lg transition-transform group-hover:scale-110",
                      accent.icon,
                    )}
                  >
                    <Icon className="h-5 w-5" />
                  </div>

                  <h3 className="mt-5 text-base font-semibold tracking-tight">
                    {t(`values.items.${value.id}.title`)}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {t(`values.items.${value.id}.body`)}
                  </p>
                </div>
              </Reveal>
            );
          })}
        </RevealGroup>
      </div>
    </section>
  );
}
