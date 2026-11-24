"use client";

import { createContext, useContext, useRef, type CSSProperties, type ReactNode } from "react";
import { useReducedMotion } from "framer-motion";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const EASE = "expo.out";

type RevealVariant =
  | "base"
  | "title"
  | "text"
  | "button"
  | "card"
  | "scaleIn"
  | "soft"
  | "fade-right"
  | "fade-left";

type Spec = { from: gsap.TweenVars; to: gsap.TweenVars; duration: number };

const SPECS: Record<RevealVariant, Spec> = {
  base: { from: { autoAlpha: 0, y: 48, scale: 0.98 }, to: { autoAlpha: 1, y: 0, scale: 1 }, duration: 0.9 },
  title: { from: { autoAlpha: 0, y: 56, scale: 0.98 }, to: { autoAlpha: 1, y: 0, scale: 1 }, duration: 0.95 },
  text: { from: { autoAlpha: 0, y: 28 }, to: { autoAlpha: 1, y: 0 }, duration: 0.75 },
  button: { from: { autoAlpha: 0, y: 20, scale: 0.98 }, to: { autoAlpha: 1, y: 0, scale: 1 }, duration: 0.65 },
  card: { from: { autoAlpha: 0, y: 36, scale: 0.98 }, to: { autoAlpha: 1, y: 0, scale: 1 }, duration: 0.8 },
  scaleIn: { from: { autoAlpha: 0, y: 24, scale: 0.94 }, to: { autoAlpha: 1, y: 0, scale: 1 }, duration: 0.9 },
  soft: { from: { autoAlpha: 0 }, to: { autoAlpha: 1 }, duration: 0.7 },
  "fade-right": { from: { autoAlpha: 0, x: -36 }, to: { autoAlpha: 1, x: 0 }, duration: 0.85 },
  "fade-left": { from: { autoAlpha: 0, x: 36 }, to: { autoAlpha: 1, x: 0 }, duration: 0.85 },
};

const InGroup = createContext(false);

interface RevealProps {
  children: ReactNode;
  variant?: RevealVariant;
  className?: string;
  style?: CSSProperties;
  delay?: number;
  standalone?: boolean;
}

export function Reveal({
  children,
  variant = "base",
  className,
  style,
  delay,
  standalone = false,
}: RevealProps) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const inGroup = useContext(InGroup);
  const self = standalone || !inGroup;

  useGSAP(
    () => {
      const el = ref.current;
      if (!el || reduced || !self) return;
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      const spec = SPECS[variant];
      gsap.from(el, {
        ...spec.from,
        duration: spec.duration,
        delay: delay ?? 0,
        ease: EASE,
        immediateRender: false,
        scrollTrigger: { trigger: el, start: "top 88%", once: true },
      });
    },
    { scope: ref, dependencies: [self, reduced, variant, delay] },
  );

  return (
    <div
      ref={ref}
      className={className}
      style={style}
      data-reveal={reduced ? undefined : variant}
      data-reveal-self={self ? "" : undefined}
      data-reveal-delay={delay}
    >
      {children}
    </div>
  );
}

interface RevealGroupProps {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  stagger?: number;
  delayChildren?: number;
}

export function RevealGroup({
  children,
  className,
  style,
  stagger = 0.12,
  delayChildren = 0,
}: RevealGroupProps) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();

  useGSAP(
    () => {
      const root = ref.current;
      if (!root || reduced) return;
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      const items = Array.from(root.querySelectorAll<HTMLElement>("[data-reveal]")).filter(
        (el) => el.closest("[data-reveal-group]") === root && !el.hasAttribute("data-reveal-self"),
      );
      if (items.length === 0) return;
      const tl = gsap.timeline({
        scrollTrigger: { trigger: root, start: "top 88%", once: true },
      });
      items.forEach((el, index) => {
        const spec = SPECS[(el.dataset.reveal as RevealVariant) || "base"] ?? SPECS.base;
        const extra = Number(el.dataset.revealDelay || 0);
        // immediateRender false: if the trigger never fires (pinned sections
        // shift later triggers), the block stays visible instead of opacity 0.
        tl.from(el, { ...spec.from, duration: spec.duration, ease: EASE, immediateRender: false }, index * stagger + delayChildren + extra);
      });
    },
    { scope: ref, dependencies: [reduced, stagger, delayChildren] },
  );

  return (
    <InGroup.Provider value={true}>
      <div ref={ref} className={className} style={style} data-reveal-group="">
        {children}
      </div>
    </InGroup.Provider>
  );
}
