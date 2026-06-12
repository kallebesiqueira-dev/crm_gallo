"use client";

import { useTranslations } from "next-intl";
import { Compass, Heart, Rocket, Sparkles } from "lucide-react";
import { Reveal, RevealGroup } from "@/components/marketing/reveal";

const TIMELINE: { yearKey: string; titleKey: string; bodyKey: string; icon: typeof Sparkles }[] = [
  { yearKey: "about.timeline.1.year", titleKey: "about.timeline.1.title", bodyKey: "about.timeline.1.body", icon: Sparkles },
  { yearKey: "about.timeline.2.year", titleKey: "about.timeline.2.title", bodyKey: "about.timeline.2.body", icon: Rocket },
  { yearKey: "about.timeline.3.year", titleKey: "about.timeline.3.title", bodyKey: "about.timeline.3.body", icon: Compass },
];

export function AboutSection() {
  const t = useTranslations("marketing");

  return (
    <section id="about" className="relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute -left-32 top-24 h-72 w-72 rounded-full bg-blue-500/10 blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -right-32 bottom-24 h-80 w-80 rounded-full bg-violet-500/10 blur-3xl"
      />

      <div className="mx-auto grid max-w-6xl gap-14 px-6 py-24 lg:grid-cols-2 lg:gap-20">
        {/* Story column — cascade: eyebrow → title → lead → body → stats */}
        <RevealGroup className="space-y-6">
          <Reveal
            variant="soft"
            className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-primary"
          >
            <Heart className="h-3 w-3" />
            {t("about.eyebrow")}
          </Reveal>
          <Reveal variant="title" className="relative">
            <span
              aria-hidden
              className="pointer-events-none absolute -inset-x-6 -inset-y-4 -z-10 rounded-[40px] bg-gradient-to-br from-blue-500/10 via-violet-500/8 to-fuchsia-500/10 blur-3xl animate-pulse-slow"
            />
            <h2 className="text-3xl font-semibold leading-tight tracking-tight sm:text-5xl">
              {t("about.title")}
            </h2>
          </Reveal>
          <Reveal variant="text" className="text-lg leading-relaxed text-foreground/80">
            {t("about.lead")}
          </Reveal>
          <Reveal variant="text" className="text-base leading-relaxed text-muted-foreground">
            {t("about.body")}
          </Reveal>

          <Reveal variant="card" className="flex justify-center pt-4">
            <div className="w-40">
              <MiniStat value={t("about.mini.1.value")} label={t("about.mini.1.label")} />
            </div>
          </Reveal>
        </RevealGroup>

        {/* Timeline / Mission card column */}
        <Reveal standalone variant="base" className="relative">
          <div className="relative overflow-hidden rounded-3xl border bg-gradient-to-br from-card via-card to-primary/5 p-8 shadow-xl shadow-primary/5">
            <div
              aria-hidden
              className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-gradient-to-br from-primary/30 to-violet-500/20 blur-2xl"
            />

            <div className="relative">
              <div className="flex items-center gap-3">
                <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-primary to-violet-500 text-primary-foreground shadow-lg shadow-primary/30">
                  <Compass className="h-5 w-5" />
                </div>
                <div>
                  <div className="text-sm font-semibold">{t("about.missionTitle")}</div>
                  <div className="text-xs text-muted-foreground">{t("about.missionSubtitle")}</div>
                </div>
              </div>

              <p className="mt-5 text-sm leading-relaxed text-foreground/90">
                {t("about.missionBody")}
              </p>

              <div className="mt-8 space-y-5 border-t pt-6">
                {TIMELINE.map((item) => {
                  const Icon = item.icon;
                  return (
                    <div key={item.yearKey} className="flex items-start gap-4">
                      <div className="relative flex flex-col items-center">
                        <div className="grid h-8 w-8 place-items-center rounded-full bg-primary/10 text-primary ring-4 ring-background">
                          <Icon className="h-3.5 w-3.5" />
                        </div>
                      </div>
                      <div className="flex-1 pb-1">
                        <div className="flex items-baseline gap-3">
                          <span className="font-mono text-xs font-semibold text-primary">
                            {t(item.yearKey)}
                          </span>
                          <span className="text-sm font-semibold">{t(item.titleKey)}</span>
                        </div>
                        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                          {t(item.bodyKey)}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function MiniStat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-xl border bg-card/60 p-3 text-center backdrop-blur-sm">
      <div className="bg-gradient-to-br from-primary to-violet-500 bg-clip-text text-2xl font-semibold tracking-tight text-transparent">
        {value}
      </div>
      <div className="mt-1 text-[11px] leading-tight text-muted-foreground">{label}</div>
    </div>
  );
}
