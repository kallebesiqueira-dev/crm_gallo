"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import Image from "next/image";
import { cn } from "@/lib/utils";

/**
 * Branded intro / preloader shown once per browser session before the landing
 * page. The GALLO CRM logo on a dark violet stage, with a CIRCULAR progress
 * ring that fills slowly to 100% (the % sits in the middle of the ring) — then
 * the whole overlay fades out to reveal the page. Rendered through a portal to
 * document.body so no ancestor stacking/clip can trap it.
 *
 * Gate: `sessionStorage["gallo-splash-seen"]` — so it greets the first view and
 * stays out of the way on SPA navigations back to the landing. Clear it (or a
 * fresh tab / incognito) to see it again.
 */
const DURATION_MS = 3000;

export function LandingSplash() {
  const [mounted, setMounted] = useState(false);
  const [show, setShow] = useState(false);
  const [progress, setProgress] = useState(0);
  const [fading, setFading] = useState(false);

  useEffect(() => {
    setMounted(true);
    if (sessionStorage.getItem("gallo-splash-seen")) return;
    sessionStorage.setItem("gallo-splash-seen", "1");
    setShow(true);
    document.body.style.overflow = "hidden";

    let raf = 0;
    let startTs: number | null = null;
    const tick = (now: number) => {
      if (startTs === null) startTs = now;
      const pct = Math.min(100, ((now - startTs) / DURATION_MS) * 100);
      setProgress(pct);
      if (pct < 100) raf = requestAnimationFrame(tick);
      else window.setTimeout(() => setFading(true), 450);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      document.body.style.overflow = "";
    };
  }, []);

  if (!mounted || !show) return null;

  const R = 26;
  const CIRC = 2 * Math.PI * R;
  const dashoffset = CIRC * (1 - progress / 100);

  return createPortal(
    <div
      className={cn(
        "fixed inset-0 z-[200] grid place-items-center transition-opacity duration-700 ease-out",
        "bg-[radial-gradient(circle_at_center,#1b0f33_0%,#0a0612_72%)]",
        fading ? "pointer-events-none opacity-0" : "opacity-100",
      )}
      onTransitionEnd={() => {
        if (fading) {
          setShow(false);
          document.body.style.overflow = "";
        }
      }}
    >
      <div className="flex flex-col items-center gap-10">
        <div className="relative">
          <div
            aria-hidden
            className="pointer-events-none absolute -inset-10 -z-10 rounded-[2.5rem] bg-violet-600/30 blur-3xl animate-pulse-slow"
          />
          <Image
            src="/gallo-logo.png"
            alt="GALLO CRM"
            width={260}
            height={260}
            priority
            className="h-auto w-44 select-none rounded-[2rem] shadow-[0_24px_70px_-12px_rgba(124,58,237,0.6)] ring-1 ring-white/10 sm:w-56"
          />
        </div>

        {/* Circular progress (the "bolinha") with the % in the center. */}
        <div className="relative h-16 w-16">
          <svg className="h-16 w-16 -rotate-90" viewBox="0 0 64 64">
            <circle cx="32" cy="32" r={R} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="4" />
            <circle
              cx="32"
              cy="32"
              r={R}
              fill="none"
              stroke="url(#galloSplashGrad)"
              strokeWidth="4"
              strokeLinecap="round"
              strokeDasharray={CIRC}
              strokeDashoffset={dashoffset}
            />
            <defs>
              <linearGradient id="galloSplashGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#a855f7" />
                <stop offset="100%" stopColor="#f5c542" />
              </linearGradient>
            </defs>
          </svg>
          <div className="absolute inset-0 grid place-items-center text-sm font-semibold tabular-nums text-white">
            {Math.round(progress)}%
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
