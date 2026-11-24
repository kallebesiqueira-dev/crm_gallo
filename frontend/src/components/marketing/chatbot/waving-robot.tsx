"use client";

import { cn } from "@/lib/utils";

/**
 * Lightweight SVG mascot. CSS floats the body, waves the right arm on load
 * and again while hovered, and pops a short greeting. Motion is disabled
 * under prefers-reduced-motion in globals.css.
 */
export function WavingRobot({
  greeting,
  compact = false,
}: {
  greeting?: string;
  compact?: boolean;
}) {
  return (
    <span className={cn("gallo-robot relative inline-flex", compact && "gallo-robot-compact")}>
      {!compact && greeting ? (
        <span className="gallo-robot-hello" aria-hidden="true">
          {greeting}
        </span>
      ) : null}
      <svg
        viewBox="0 0 88 104"
        className={cn(
          "gallo-robot-body drop-shadow-[0_8px_18px_rgba(76,29,149,0.45)]",
          compact ? "h-9 w-9" : "h-16 w-16 sm:h-[5.5rem] sm:w-[5.5rem]",
        )}
        aria-hidden="true"
      >
        <line x1="44" y1="22" x2="44" y2="12" stroke="#c4b5fd" strokeWidth="2" strokeLinecap="round" />
        <circle cx="44" cy="9" r="4" fill="#f0abfc" />
        <rect x="24" y="22" width="40" height="32" rx="14" fill="#7c3aed" />
        <rect x="28" y="26" width="32" height="22" rx="10" fill="#1e1b4b" />
        <g className="gallo-robot-eyes">
          <circle cx="37" cy="37" r="3.2" fill="#fff" />
          <circle cx="51" cy="37" r="3.2" fill="#fff" />
          <circle cx="37.8" cy="37.2" r="1.3" fill="#312e81" />
          <circle cx="51.8" cy="37.2" r="1.3" fill="#312e81" />
        </g>
        <path d="M36 43.5 Q44 48 52 43.5" fill="none" stroke="#ddd6fe" strokeWidth="1.6" strokeLinecap="round" />
        <rect x="30" y="58" width="28" height="26" rx="10" fill="#6d28d9" />
        <circle cx="44" cy="70" r="3" fill="#fde68a" />
        <rect x="14" y="62" width="12" height="22" rx="6" fill="#8b5cf6" />
        <g className="gallo-robot-arm">
          <rect x="62" y="60" width="12" height="20" rx="6" fill="#c4b5fd" />
          <circle cx="68" cy="84" r="5" fill="#f5f3ff" />
        </g>
        <rect x="34" y="86" width="8" height="12" rx="3" fill="#5b21b6" />
        <rect x="46" y="86" width="8" height="12" rx="3" fill="#5b21b6" />
      </svg>
    </span>
  );
}
