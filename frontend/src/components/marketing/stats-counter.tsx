"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Reveal, RevealGroup } from "@/components/marketing/reveal";

interface Stat {
  value: number;
  suffix?: string;
  labelKey: string;
}

const STATS: Stat[] = [
  { value: 10000, suffix: "+", labelKey: "statsLeads" },
  { value: 7, labelKey: "statsLanguages" },
  { value: 99.9, suffix: "%", labelKey: "statsUptime" },
  { value: 100, suffix: "%", labelKey: "statsOpenSource" },
];

function useCountUp(target: number, durationMs = 1400, start = false): number {
  const [value, setValue] = useState(0);
  const startTimeRef = useRef<number | null>(null);
  useEffect(() => {
    if (!start) return;
    let raf = 0;
    const tick = (now: number) => {
      if (startTimeRef.current == null) startTimeRef.current = now;
      const elapsed = now - startTimeRef.current;
      const progress = Math.min(1, elapsed / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(target * eased);
      if (progress < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, durationMs, start]);
  return value;
}

export function StatsCounter() {
  const t = useTranslations("marketing");
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setVisible(true);
          io.disconnect();
        }
      },
      { threshold: 0.3 },
    );
    io.observe(node);
    return () => io.disconnect();
  }, []);

  return (
    <section ref={ref}>
      <div className="mx-auto max-w-6xl px-6 py-16">
        <RevealGroup
          className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4"
          stagger={0.12}
        >
          {STATS.map((stat) => (
            <Reveal key={stat.labelKey} variant="card">
              <StatTile stat={stat} start={visible} label={t(stat.labelKey)} />
            </Reveal>
          ))}
        </RevealGroup>
      </div>
    </section>
  );
}

function StatTile({ stat, start, label }: { stat: Stat; start: boolean; label: string }) {
  const animated = useCountUp(stat.value, 1400, start);
  const display =
    stat.value % 1 === 0
      ? Math.floor(animated).toLocaleString()
      : animated.toFixed(1);

  return (
    <div className="text-center">
      <div className="bg-gradient-to-br from-primary to-violet-500 bg-clip-text text-5xl font-semibold tracking-tight text-transparent sm:text-6xl">
        {display}
        {stat.suffix && <span>{stat.suffix}</span>}
      </div>
      <div className="mt-2 text-sm text-muted-foreground">{label}</div>
    </div>
  );
}
