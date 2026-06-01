"use client";

import { useEffect } from "react";
import Lenis from "lenis";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

/**
 * Mounts a single Lenis instance that drives smooth-scroll for the whole
 * subtree. Lenis interpolates wheel/touch events, so scrolling feels
 * buttery — the standard "premium SaaS" effect (Stripe, Linear, Apple).
 *
 * Lenis is wired into GSAP's ticker so ScrollTrigger reads positions
 * from Lenis's transformed scroll, not the raw window scroll. Without
 * this wiring, ScrollTrigger triggers fire at the wrong moments.
 *
 * Respects `prefers-reduced-motion`: if the user opted out of motion,
 * we skip Lenis entirely and let the browser scroll natively.
 */
export function SmoothScroll({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    if (typeof window === "undefined") return;

    // Respect accessibility setting — skip smooth scroll for users who
    // prefer reduced motion (vestibular disorders, attention sensitivity).
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }

    gsap.registerPlugin(ScrollTrigger);

    const lenis = new Lenis({
      duration: 1.4,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
      wheelMultiplier: 0.9,
      touchMultiplier: 1.5,
    });

    // Sync Lenis with GSAP's ticker — ScrollTrigger reads from the same
    // RAF loop, so triggers fire at the right moment.
    lenis.on("scroll", ScrollTrigger.update);

    const raf = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(raf);
    gsap.ticker.lagSmoothing(0);

    return () => {
      gsap.ticker.remove(raf);
      lenis.destroy();
    };
  }, []);

  return <>{children}</>;
}
