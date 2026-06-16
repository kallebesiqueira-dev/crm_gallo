"use client";

import { Check, Smartphone } from "lucide-react";
import { useTranslations } from "next-intl";
import { Flag } from "@/components/flag-icon";
import { Reveal } from "@/components/marketing/reveal";

/**
 * Mobile showcase — a portrait screen recording of GALLO CRM running on a
 * phone, framed in a small device mockup, beside copy about the responsive,
 * 7-language UI. The greeting chips (one per supported locale) carry the
 * "speaks your language" point visually and stay untranslated by design.
 *
 * Swap the clip by replacing `public/mobile_demo.mp4` — no code change.
 */
const MOBILE_VIDEO = "/mobile_demo.mp4";

// One greeting per supported locale (en·pt·es·fr·it·de·rm). Flag codes map to
// the inline SVGs in <Flag>: GB·BR·ES·FR·IT·DE·CH.
const GREETINGS: { code: string; word: string }[] = [
  { code: "GB", word: "Hello" },
  { code: "BR", word: "Olá" },
  { code: "ES", word: "Hola" },
  { code: "FR", word: "Bonjour" },
  { code: "IT", word: "Ciao" },
  { code: "DE", word: "Hallo" },
  { code: "CH", word: "Allegra" },
];

export function MobileShowcase() {
  const t = useTranslations("marketing.mobileShowcase");
  const points = [t("point1"), t("point2"), t("point3")];

  return (
    <section className="relative overflow-hidden py-16">
      {/* Ambient glow, matching the desktop showcase section. */}
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-1/2 -z-10 h-[32rem] w-[48rem] max-w-full -translate-x-1/2 -translate-y-1/2 rounded-full bg-gradient-to-br from-violet-500/15 via-fuchsia-500/10 to-blue-500/15 blur-3xl"
      />
      <Reveal
        standalone
        variant="scaleIn"
        className="relative mx-auto grid max-w-5xl grid-cols-1 items-center gap-10 px-6 md:grid-cols-2"
      >
        {/* Phone mockup — kept deliberately small. Order flips so the copy
            leads on mobile and the device sits beside it on desktop. */}
        <div className="order-2 flex justify-center md:order-1">
          <div className="relative aspect-[384/848] w-[220px] overflow-hidden rounded-[2.25rem] border-[6px] border-slate-800 bg-slate-900 shadow-2xl shadow-violet-500/20 ring-1 ring-white/10 sm:w-[250px]">
            {/* Notch */}
            <div className="absolute left-1/2 top-0 z-10 h-5 w-24 -translate-x-1/2 rounded-b-2xl bg-slate-800" />
            <video
              className="h-full w-full object-cover"
              autoPlay
              muted
              loop
              playsInline
              preload="metadata"
              aria-label="GALLO CRM running on a mobile phone"
            >
              <source src={MOBILE_VIDEO} type="video/mp4" />
            </video>
          </div>
        </div>

        {/* Copy */}
        <div className="order-1 md:order-2">
          <span className="inline-flex items-center gap-2 rounded-full border border-violet-500/30 bg-violet-500/10 px-3 py-1 text-xs font-medium text-violet-300">
            <Smartphone className="h-3.5 w-3.5" />
            {t("badge")}
          </span>
          <h2 className="mt-4 bg-gradient-to-r from-white to-slate-300 bg-clip-text text-3xl font-bold tracking-tight text-transparent sm:text-4xl dark:from-white dark:to-slate-300">
            {t("headline")}
          </h2>
          <p className="mt-4 max-w-md text-base text-slate-400">{t("description")}</p>

          <ul className="mt-6 space-y-3">
            {points.map((p) => (
              <li key={p} className="flex items-start gap-3 text-sm text-slate-300">
                <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-emerald-500/15 text-emerald-400">
                  <Check className="h-3 w-3" />
                </span>
                {p}
              </li>
            ))}
          </ul>

          {/* 7-language greeting chips */}
          <div className="mt-7 flex flex-wrap gap-2">
            {GREETINGS.map((g) => (
              <span
                key={g.code}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-200"
              >
                <Flag code={g.code} className="h-3.5 w-5 shrink-0 rounded-sm ring-1 ring-black/10" />
                {g.word}
              </span>
            ))}
          </div>
        </div>
      </Reveal>
    </section>
  );
}
