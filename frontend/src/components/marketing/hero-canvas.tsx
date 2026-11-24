"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

const HeroScene = dynamic(
  () => import("@/components/marketing/hero-scene").then((mod) => mod.HeroScene),
  { ssr: false },
);

/**
 * Lazy 3D hero. Mounts after idle, caps DPR, pauses when off-screen,
 * and stays unmounted when the user prefers reduced motion.
 */
export function HeroCanvas() {
  const ref = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [active, setActive] = useState(false);
  const [dpr, setDpr] = useState(1);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const arm = () => {
      const cap = window.innerWidth < 768 ? 1 : Math.min(window.devicePixelRatio || 1, 1.5);
      setDpr(cap);
      setReady(true);
    };
    const idleId = window.requestIdleCallback(arm, { timeout: 1500 });

    const node = ref.current;
    const observer = new IntersectionObserver(
      ([entry]) => setActive(entry.isIntersecting),
      { threshold: 0.08 },
    );
    if (node) observer.observe(node);

    return () => {
      window.cancelIdleCallback(idleId);
      observer.disconnect();
    };
  }, []);

  return (
    <div ref={ref} className="pointer-events-none absolute inset-0 -z-10" aria-hidden>
      {ready ? <HeroScene active={active} dpr={dpr} /> : null}
    </div>
  );
}
