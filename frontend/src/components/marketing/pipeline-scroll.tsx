"use client";

import { useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { useTranslations } from "next-intl";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const STEP_IDS = ["capture", "work", "propose", "close"] as const;

export function PipelineScroll() {
  const root = useRef<HTMLElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const t = useTranslations("marketing.scroll");

  useGSAP(
    () => {
      const section = root.current;
      const row = track.current;
      if (!section || !row) return;
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      if (window.matchMedia("(max-width: 767px)").matches) return;

      const tween = gsap.to(row, {
        xPercent: -75,
        ease: "none",
        scrollTrigger: {
          trigger: section,
          pin: true,
          scrub: 0.6,
          start: "top top",
          end: "+=2200",
          invalidateOnRefresh: true,
        },
      });
      return () => {
        tween.scrollTrigger?.kill();
        tween.kill();
      };
    },
    { scope: root },
  );

  return (
    <section id="path" ref={root} className="relative">
      <div className="overflow-hidden">
        <div
          ref={track}
          className="flex flex-col gap-4 px-6 py-20 md:h-dvh md:w-[400%] md:flex-row md:items-center md:gap-0 md:px-0 md:py-0"
        >
          {STEP_IDS.map((id, index) => (
            <article
              key={id}
              className="mx-auto flex w-full max-w-xl flex-col justify-center md:w-1/4 md:max-w-none md:px-[8vw]"
            >
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-violet-300/80">
                {t("eyebrow")} · 0{index + 1}
              </p>
              {index === 0 ? (
                <h2 className="mt-4 max-w-md text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
                  {t("title")}
                </h2>
              ) : null}
              <h3
                className={
                  index === 0
                    ? "mt-6 text-lg font-medium text-foreground"
                    : "mt-4 text-4xl font-semibold tracking-tight text-foreground sm:text-5xl"
                }
              >
                {t(`steps.${id}.title`)}
              </h3>
              <p className="mt-4 max-w-md text-base leading-relaxed text-muted-foreground sm:text-lg">
                {t(`steps.${id}.body`)}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
