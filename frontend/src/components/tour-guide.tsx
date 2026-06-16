"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslations } from "next-intl";
import { Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * First-run guided tour (roadmap #2). Auto-starts once per browser
 * (localStorage) a moment after the app shell paints, and can be replayed
 * anytime via the `gallo:tour-start` window event (wired to the Help menu).
 *
 * It spotlights real UI elements tagged with `data-tour="<id>"`. A step whose
 * target is missing or hidden at the current breakpoint (e.g. the desktop
 * sidebar vs the mobile hamburger) falls back to a centered card, so the tour
 * never points at nothing. Rendered through a portal to `document.body` so the
 * fixed overlay escapes the header's `backdrop-blur` containing block (same
 * trap the mobile nav hit).
 */
const DONE_KEY = "gallo_tour_done_v1";
const PAD = 8;
const TIP_W = 340;

type Step = { target?: string; titleKey: string; bodyKey: string };

const STEPS: Step[] = [
  { titleKey: "welcomeTitle", bodyKey: "welcomeBody" },
  { target: "nav", titleKey: "navTitle", bodyKey: "navBody" },
  { target: "assistant", titleKey: "assistantTitle", bodyKey: "assistantBody" },
  { target: "checklist", titleKey: "createTitle", bodyKey: "createBody" },
  { titleKey: "doneTitle", bodyKey: "doneBody" },
];

export function TourGuide() {
  const t = useTranslations("tour");
  const [mounted, setMounted] = useState(false);
  const [active, setActive] = useState(false);
  const [idx, setIdx] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => setMounted(true), []);

  // Auto-start once, shortly after mount so the dashboard has painted.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (localStorage.getItem(DONE_KEY)) return;
    const id = window.setTimeout(() => setActive(true), 1000);
    return () => window.clearTimeout(id);
  }, []);

  // Replay from the Help menu.
  useEffect(() => {
    const onStart = () => {
      setIdx(0);
      setActive(true);
    };
    window.addEventListener("gallo:tour-start", onStart);
    return () => window.removeEventListener("gallo:tour-start", onStart);
  }, []);

  const step = STEPS[idx];

  const measure = useCallback(() => {
    if (!step?.target) {
      setRect(null);
      return null;
    }
    const els = Array.from(
      document.querySelectorAll<HTMLElement>(`[data-tour="${step.target}"]`),
    );
    const el = els.find((e) => e.offsetParent !== null) ?? null;
    setRect(el ? el.getBoundingClientRect() : null);
    return el;
  }, [step]);

  // On step change: scroll the target into view, then measure. Keep it pinned
  // to the (possibly scrolling) element while the step is open.
  useEffect(() => {
    if (!active) return;
    const el = measure();
    if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
    const t1 = window.setTimeout(measure, 300);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    document.body.style.overflow = "hidden";
    return () => {
      window.clearTimeout(t1);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
      document.body.style.overflow = "";
    };
  }, [active, measure]);

  function close() {
    localStorage.setItem(DONE_KEY, "1");
    setActive(false);
    setIdx(0);
    setRect(null);
  }

  if (!mounted || !active) return null;

  const isLast = idx === STEPS.length - 1;
  const isFirst = idx === 0;

  // Tooltip placement: below the target if it fits, else above; centered when
  // there's no target.
  let tip: React.CSSProperties;
  if (rect) {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const w = Math.min(TIP_W, vw - 32);
    const left = Math.max(16, Math.min(rect.left + rect.width / 2 - w / 2, vw - w - 16));
    const fitsBelow = rect.bottom + 230 < vh;
    tip = fitsBelow
      ? { top: rect.bottom + 12, left, width: w }
      : { top: rect.top - 12, left, width: w, transform: "translateY(-100%)" };
  } else {
    tip = {
      top: "50%",
      left: "50%",
      transform: "translate(-50%, -50%)",
      width: `min(${TIP_W}px, calc(100vw - 2rem))`,
    };
  }

  return createPortal(
    <div
      className="fixed inset-0 z-[200]"
      role="dialog"
      aria-modal="true"
      aria-label={t("welcomeTitle")}
    >
      {/* Dim + spotlight. The full-screen layer blocks page interaction; the
          ring is purely visual (pointer-events-none). */}
      {rect ? (
        <div
          className="pointer-events-none absolute rounded-xl ring-2 ring-primary transition-all duration-300"
          style={{
            top: rect.top - PAD,
            left: rect.left - PAD,
            width: rect.width + PAD * 2,
            height: rect.height + PAD * 2,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.65)",
          }}
        />
      ) : (
        <div className="absolute inset-0 bg-black/65" />
      )}

      {/* Tooltip card */}
      <div
        className="absolute rounded-xl border bg-popover p-4 text-popover-foreground shadow-2xl"
        style={tip}
      >
        <button
          type="button"
          onClick={close}
          aria-label={t("skip")}
          className="absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
        <div className="mb-2 flex items-center gap-2 text-primary">
          <Sparkles className="h-4 w-4 shrink-0" />
          <span className="text-xs font-medium">
            {t("progress", { step: idx + 1, total: STEPS.length })}
          </span>
        </div>
        <h3 className="pr-6 text-base font-semibold">{t(step.titleKey)}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{t(step.bodyKey)}</p>
        <div className="mt-4 flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={close}
            className="text-xs font-medium text-muted-foreground transition hover:text-foreground"
          >
            {t("skip")}
          </button>
          <div className="flex items-center gap-2">
            {!isFirst && (
              <Button type="button" variant="outline" size="sm" onClick={() => setIdx((n) => n - 1)}>
                {t("back")}
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              onClick={() => (isLast ? close() : setIdx((n) => n + 1))}
            >
              {isLast ? t("done") : t("next")}
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
