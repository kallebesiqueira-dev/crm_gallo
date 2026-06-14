"use client";

import {
  Bot,
  Check,
  ChevronRight,
  Globe,
  Layers,
  LineChart,
  Lock,
  MessagesSquare,
  Sparkles,
  Target,
  TrendingUp,
  Workflow,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { Reveal, RevealGroup } from "@/components/marketing/reveal";
import { Flag } from "@/components/flag-icon";

type Feature = {
  id: string;
  side: "left" | "right";
  icon: typeof Bot;
  accent: "blue" | "violet" | "emerald";
  mockup: "ai" | "pipeline" | "intl";
};

const FEATURES: Feature[] = [
  { id: "ai", side: "right", icon: Bot, accent: "violet", mockup: "ai" },
  { id: "pipeline", side: "left", icon: Workflow, accent: "blue", mockup: "pipeline" },
  { id: "intl", side: "right", icon: Globe, accent: "emerald", mockup: "intl" },
];

const ACCENT: Record<string, { bg: string; ring: string; text: string }> = {
  blue: { bg: "from-blue-500/15 to-blue-500/0", ring: "ring-blue-500/20", text: "text-blue-500" },
  violet: {
    bg: "from-violet-500/15 via-fuchsia-500/10 to-transparent",
    ring: "ring-violet-500/20",
    text: "text-violet-500",
  },
  emerald: {
    bg: "from-emerald-500/15 to-emerald-500/0",
    ring: "ring-emerald-500/20",
    text: "text-emerald-500",
  },
};

export function FeatureSections() {
  const t = useTranslations("marketing");
  return (
    <section className="space-y-24 py-24">
      {FEATURES.map((feature) => {
        const Icon = feature.icon;
        const accent = ACCENT[feature.accent];
        return (
          <div key={feature.id} className="mx-auto max-w-6xl px-6">
            <div
              className={cn(
                "grid items-center gap-12 lg:grid-cols-2 lg:gap-16",
                feature.side === "left" && "lg:[&>*:first-child]:order-2",
              )}
            >
              {/* Mockup — heavier glassmorphism + premium hover lift */}
              <Reveal
                standalone
                variant="scaleIn"
                className={cn(
                  "group relative rounded-2xl border bg-card/70 p-6 shadow-xl shadow-primary/5 ring-1 backdrop-blur-xl",
                  "transition-all duration-[250ms] hover:-translate-y-1.5 hover:scale-[1.02] hover:shadow-2xl hover:shadow-primary/15",
                  accent.ring,
                )}
              >
                <div
                  aria-hidden
                  className={cn(
                    "pointer-events-none absolute inset-0 rounded-2xl bg-gradient-to-br",
                    accent.bg,
                  )}
                />
                <div className="relative">
                  {feature.mockup === "ai" && <AiMockup />}
                  {feature.mockup === "pipeline" && <PipelineMockup />}
                  {feature.mockup === "intl" && <IntlMockup />}
                </div>
              </Reveal>

              {/* Copy — cascade: eyebrow → title → body → bullets */}
              <RevealGroup className="space-y-5">
                <Reveal
                  variant="soft"
                  className={cn(
                    "inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-medium",
                    accent.text,
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {t(`feature.${feature.id}.eyebrow`)}
                </Reveal>
                <Reveal variant="title" className="relative">
                  <span
                    aria-hidden
                    className={cn(
                      "pointer-events-none absolute -inset-x-6 -inset-y-4 -z-10 rounded-[40px] blur-3xl animate-pulse-slow opacity-50",
                      accent.bg,
                    )}
                  />
                  <h3 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                    {t(`feature.${feature.id}.title`)}
                  </h3>
                </Reveal>
                <Reveal variant="text" className="text-base text-muted-foreground">
                  {t(`feature.${feature.id}.body`)}
                </Reveal>
                <Reveal variant="text">
                  <ul className="space-y-2">
                    {[1, 2, 3].map((i) => (
                      <li key={i} className="flex items-start gap-2 text-sm">
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                        <span>{t(`feature.${feature.id}.bullet.${i}`)}</span>
                      </li>
                    ))}
                  </ul>
                </Reveal>
              </RevealGroup>
            </div>
          </div>
        );
      })}
    </section>
  );
}

/* ------------- Tiny mockups ------------- */

function AiMockup() {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white">
          <Sparkles className="h-4 w-4" />
        </div>
        <div>
          <div className="text-sm font-semibold">AI Sales Assistant</div>
          <div className="text-[10px] text-muted-foreground">Powered by advanced AI</div>
        </div>
      </div>

      <div className="space-y-2 rounded-lg border bg-background/60 p-3">
        <div className="flex items-start gap-2">
          <div className="h-6 w-6 shrink-0 rounded-full bg-gradient-to-br from-pink-400 to-rose-500" />
          <div className="rounded-lg rounded-tl-sm bg-muted px-3 py-1.5 text-xs">
            Draft a follow-up email to Sofia mentioning the proposal
          </div>
        </div>
        <div className="flex items-start gap-2">
          <div className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white">
            <Sparkles className="h-3 w-3" />
          </div>
          <div className="space-y-1 rounded-lg rounded-tl-sm bg-violet-500/10 px-3 py-2 text-xs">
            <div className="font-medium">Subject: Pricing proposal · Gallo CRM Premium</div>
            <div className="text-muted-foreground">
              Hi Sofia, thanks for the demo today. Following up with the pricing breakdown we discussed — annual plan saves you 20%…
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2">
        <div className="flex items-center gap-2 text-xs">
          <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />
          <span className="font-medium">AI score: 87 / 100</span>
        </div>
        <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-300">
          High priority
        </span>
      </div>
    </div>
  );
}

function PipelineMockup() {
  const columns = [
    { label: "New", color: "bg-indigo-500/15 text-indigo-600", count: 12 },
    { label: "Qualified", color: "bg-teal-500/15 text-teal-600", count: 8 },
    { label: "Negotiation", color: "bg-amber-500/15 text-amber-600", count: 5 },
    { label: "Won", color: "bg-emerald-500/15 text-emerald-600", count: 3 },
  ];
  const cards = [
    { title: "Acme – Annual Plan", value: "€18,400", prob: 80 },
    { title: "Globex – Pilot", value: "€6,200", prob: 45 },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold">Pipeline · Drag to move</div>
        <span className="text-[10px] text-muted-foreground">€421,800 · 28 deals</span>
      </div>
      <div className="grid grid-cols-4 gap-2">
        {columns.map((c) => (
          <div key={c.label} className="rounded-md border bg-background/60 p-2">
            <div className="flex items-center justify-between">
              <span className={`rounded px-1.5 py-0.5 text-[9px] font-medium ${c.color}`}>
                {c.label}
              </span>
              <span className="text-[9px] text-muted-foreground">{c.count}</span>
            </div>
            <div className="mt-2 space-y-1">
              {cards.slice(0, c.label === "Qualified" ? 2 : 1).map((d, i) => (
                <div
                  key={i}
                  className={cn(
                    "rounded border bg-card p-1.5",
                    c.label === "Qualified" && i === 0 && "rotate-[1.5deg] shadow-lg ring-2 ring-primary/40",
                  )}
                >
                  <div className="truncate text-[9px] font-medium">{d.title}</div>
                  <div className="mt-0.5 flex items-center justify-between text-[8px] text-muted-foreground">
                    <span className="font-mono">{d.value}</span>
                    <span>{d.prob}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2 rounded border border-dashed bg-background/40 p-2 text-[10px] text-muted-foreground">
        <Target className="h-3 w-3" />
        Forecast: <span className="font-mono text-foreground">€124k</span> closing this month
      </div>
    </div>
  );
}

function IntlMockup() {
  const locales = [
    { code: "GB", label: "English" },
    { code: "BR", label: "Português" },
    { code: "DE", label: "Deutsch" },
    { code: "FR", label: "Français" },
    { code: "IT", label: "Italiano" },
    { code: "ES", label: "Español" },
    { code: "CH", label: "Rumantsch" },
  ];
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-500 text-white">
          <Globe className="h-4 w-4" />
        </div>
        <div>
          <div className="text-sm font-semibold">7 native languages</div>
          <div className="text-[10px] text-muted-foreground">UI + AI + emails</div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {locales.map((l) => (
          <div
            key={l.label}
            className="flex items-center gap-2 rounded-md border bg-background/60 px-2 py-1.5 text-xs"
          >
            <Flag code={l.code} className="h-4 w-6 shrink-0 rounded-sm ring-1 ring-black/10" />
            <span className="font-medium">{l.label}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-xs">
        <div className="flex items-center gap-2">
          <Lock className="h-3.5 w-3.5 text-emerald-500" />
          <span className="font-medium">GDPR ready · AGPL-3.0</span>
        </div>
        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
      </div>
    </div>
  );
}
