"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

const AtmosphereScene = dynamic(
  () => import("@/components/marketing/atmosphere-scene").then((m) => m.AtmosphereScene),
  { ssr: false },
);

/** Lazy WebGL dust field behind the landing. Skipped when motion is reduced. */
export function LandingAtmosphere() {
  const ref = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [active, setActive] = useState(false);
  const [dpr, setDpr] = useState(1);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const arm = () => {
      setDpr(window.innerWidth < 768 ? 1 : Math.min(window.devicePixelRatio || 1, 1.25));
      setReady(true);
    };
    const idleId = window.requestIdleCallback(arm, { timeout: 1600 });
    const node = ref.current;
    let seen = true;
    const sync = () => setActive(seen && document.visibilityState === "visible");
    const observer = new IntersectionObserver(([entry]) => {
      seen = entry.isIntersecting;
      sync();
    }, { threshold: 0 });
    if (node) observer.observe(node);
    document.addEventListener("visibilitychange", sync);
    return () => {
      window.cancelIdleCallback(idleId);
      observer.disconnect();
      document.removeEventListener("visibilitychange", sync);
    };
  }, []);

  return (
    <div ref={ref} aria-hidden className="pointer-events-none absolute inset-0 z-0">
      {ready ? <AtmosphereScene active={active} dpr={dpr} /> : null}
    </div>
  );
}
