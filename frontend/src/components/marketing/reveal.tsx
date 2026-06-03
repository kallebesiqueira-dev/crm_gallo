"use client";

import { motion, useReducedMotion, type Variants } from "framer-motion";
import { type CSSProperties, type ReactNode } from "react";

/**
 * Premium scroll-reveal primitives — Framer Motion edition.
 *
 *   FROM:  opacity 0,  blur(28px),  translateY(90px) scale(0.97)
 *   TO:    opacity 1,  blur(0px),   translateY(0)    scale(1)
 *
 * Easing cubic-bezier(0.16, 1, 0.3, 1) — the "expo.out" curve favoured by
 * Linear/Vercel/Stripe/Framer for marketing reveals. Duration 1.6s for the
 * main feel; lighter variants trim it slightly so they never lag behind
 * the title they're paired with.
 *
 * Trigger fires once per element at `amount: 0.25` (element must be 25%
 * inside the viewport). Respects `prefers-reduced-motion` — snaps to
 * final state with zero animation when honoured.
 */

const EASE = [0.16, 1, 0.3, 1] as const;
const DURATION_BASE = 1.6;
const DURATION_TEXT = 1.3;
const DURATION_BUTTON = 1.1;
const STAGGER = 0.12;
const VIEWPORT_AMOUNT = 0.25;

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

const REVEAL_VARIANTS: Record<RevealVariant, Variants> = {
  base: {
    hidden: { opacity: 0, y: 90, scale: 0.97, filter: "blur(28px)" },
    visible: {
      opacity: 1,
      y: 0,
      scale: 1,
      filter: "blur(0px)",
      transition: { duration: DURATION_BASE, ease: EASE },
    },
  },
  // Title: full y/scale, blur dissipates over the full duration so
  // headlines visibly "emerge from fog" — the cinematic ask.
  title: {
    hidden: { opacity: 0, y: 90, scale: 0.97, filter: "blur(28px)" },
    visible: {
      opacity: 1,
      y: 0,
      scale: 1,
      filter: "blur(0px)",
      transition: { duration: DURATION_BASE, ease: EASE },
    },
  },
  // Text: shorter rise (60px), trimmer duration — catches up to the
  // preceding title inside a 120ms stagger.
  text: {
    hidden: { opacity: 0, y: 60, filter: "blur(20px)" },
    visible: {
      opacity: 1,
      y: 0,
      filter: "blur(0px)",
      transition: { duration: DURATION_TEXT, ease: EASE },
    },
  },
  // Button: minimal rise (40px), slight scale — pops into place last.
  button: {
    hidden: { opacity: 0, y: 40, scale: 0.96, filter: "blur(14px)" },
    visible: {
      opacity: 1,
      y: 0,
      scale: 1,
      filter: "blur(0px)",
      transition: { duration: DURATION_BUTTON, ease: EASE },
    },
  },
  // Card: full premium reveal, used inside <RevealGroup> grids.
  card: {
    hidden: { opacity: 0, y: 70, scale: 0.96, filter: "blur(22px)" },
    visible: {
      opacity: 1,
      y: 0,
      scale: 1,
      filter: "blur(0px)",
      transition: { duration: DURATION_BASE, ease: EASE },
    },
  },
  // Scale-in: subtle inward zoom for wide hero visuals.
  scaleIn: {
    hidden: { opacity: 0, scale: 0.92, y: 30, filter: "blur(22px)" },
    visible: {
      opacity: 1,
      scale: 1,
      y: 0,
      filter: "blur(0px)",
      transition: { duration: 1.5, ease: EASE },
    },
  },
  // Soft: opacity + blur only, no transform. Use for ambient elements
  // we don't want to physically move (eyebrows, ribbons, accents).
  soft: {
    hidden: { opacity: 0, filter: "blur(20px)" },
    visible: {
      opacity: 1,
      filter: "blur(0px)",
      transition: { duration: DURATION_TEXT, ease: EASE },
    },
  },
  // Directional fades for side-by-side lockups (e.g. the comparison
  // cards): each slides horizontally into place so the pair converges.
  "fade-right": {
    hidden: { opacity: 0, x: -60, filter: "blur(20px)" },
    visible: {
      opacity: 1,
      x: 0,
      filter: "blur(0px)",
      transition: { duration: DURATION_BASE, ease: EASE },
    },
  },
  "fade-left": {
    hidden: { opacity: 0, x: 60, filter: "blur(20px)" },
    visible: {
      opacity: 1,
      x: 0,
      filter: "blur(0px)",
      transition: { duration: DURATION_BASE, ease: EASE },
    },
  },
};

interface RevealProps {
  children: ReactNode;
  variant?: RevealVariant;
  className?: string;
  style?: CSSProperties;
  /** Extra delay on top of any parent stagger, in seconds. */
  delay?: number;
  /**
   * When this Reveal lives inside a <RevealGroup>, leave standalone=false
   * (default) so it inherits the group's viewport observer. Set true to
   * give it its own observer — useful when it should animate independent
   * of any group.
   */
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
  const prefersReducedMotion = useReducedMotion();

  // Apply per-element delay by extending the variant's transition.
  const baseVariant = REVEAL_VARIANTS[variant];
  const variants = delay ? withDelay(baseVariant, delay) : baseVariant;

  // Reduced motion: render in the final state, skip animation entirely.
  if (prefersReducedMotion) {
    return (
      <div className={className} style={style}>
        {children}
      </div>
    );
  }

  // Standalone gets its own viewport trigger; otherwise it inherits the
  // RevealGroup's animate state through Framer's variant cascade.
  const standaloneProps = standalone
    ? {
        initial: "hidden" as const,
        whileInView: "visible" as const,
        viewport: { once: true, amount: VIEWPORT_AMOUNT },
      }
    : {};

  return (
    <motion.div
      className={className}
      style={{ willChange: "transform, filter, opacity", ...style }}
      variants={variants}
      {...standaloneProps}
    >
      {children}
    </motion.div>
  );
}

interface RevealGroupProps {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  /** Override stagger between children (seconds). Default 0.12 (120ms). */
  stagger?: number;
  /** Delay before the first child starts (seconds). */
  delayChildren?: number;
}

/**
 * Orchestrates a cascade of <Reveal> children with 120ms stagger by
 * default. One viewport observer for the whole group — cheaper than per-
 * element observers, perfectly synced, animates in DOM order.
 * Put children in title → text → buttons → cards order to match the
 * intended reveal sequence.
 */
export function RevealGroup({
  children,
  className,
  style,
  stagger = STAGGER,
  delayChildren = 0,
}: RevealGroupProps) {
  const prefersReducedMotion = useReducedMotion();

  if (prefersReducedMotion) {
    return (
      <div className={className} style={style}>
        {children}
      </div>
    );
  }

  const groupVariants: Variants = {
    hidden: {},
    visible: {
      transition: { staggerChildren: stagger, delayChildren },
    },
  };

  return (
    <motion.div
      className={className}
      style={style}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: VIEWPORT_AMOUNT }}
      variants={groupVariants}
    >
      {children}
    </motion.div>
  );
}

function withDelay(variant: Variants, delay: number): Variants {
  const visible = (variant.visible ?? {}) as { transition?: object };
  return {
    hidden: variant.hidden,
    visible: {
      ...visible,
      transition: {
        ...(visible.transition ?? {}),
        delay,
      },
    },
  };
}

// Constants exported so consumers can match the system feel when they
// need a one-off custom orchestration (e.g. the layered dashboard reveal).
export const REVEAL_EASE = EASE;
export const REVEAL_DURATION = DURATION_BASE;
export const REVEAL_STAGGER = STAGGER;
export const REVEAL_VIEWPORT_AMOUNT = VIEWPORT_AMOUNT;
