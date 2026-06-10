import type { ReactNode } from "react";

/**
 * Tiny inline SVG flags (3:2). We use these instead of emoji flags because
 * Windows renders flag emoji as their 2-letter code (🇬🇧 → "GB"), which made the
 * language card look broken. Inline SVG renders identically on every OS, needs
 * no dependency, and is simplified just enough to stay crisp at ~16px wide.
 */
const FLAGS: Record<string, ReactNode> = {
  GB: (
    <>
      <rect width="60" height="40" fill="#012169" />
      <path d="M0 0 60 40 M60 0 0 40" stroke="#fff" strokeWidth="8" fill="none" />
      <path d="M0 0 60 40 M60 0 0 40" stroke="#C8102E" strokeWidth="4" fill="none" />
      <path d="M30 0 V40 M0 20 H60" stroke="#fff" strokeWidth="12" fill="none" />
      <path d="M30 0 V40 M0 20 H60" stroke="#C8102E" strokeWidth="7" fill="none" />
    </>
  ),
  BR: (
    <>
      <rect width="60" height="40" fill="#009B3A" />
      <polygon points="30,4 56,20 30,36 4,20" fill="#FEDF00" />
      <circle cx="30" cy="20" r="8.5" fill="#002776" />
    </>
  ),
  DE: (
    <>
      <rect width="60" height="40" fill="#000" />
      <rect y="13.33" width="60" height="13.33" fill="#DD0000" />
      <rect y="26.66" width="60" height="13.34" fill="#FFCE00" />
    </>
  ),
  FR: (
    <>
      <rect width="60" height="40" fill="#fff" />
      <rect width="20" height="40" fill="#0055A4" />
      <rect x="40" width="20" height="40" fill="#EF4135" />
    </>
  ),
  IT: (
    <>
      <rect width="60" height="40" fill="#fff" />
      <rect width="20" height="40" fill="#009246" />
      <rect x="40" width="20" height="40" fill="#CE2B37" />
    </>
  ),
  ES: (
    <>
      <rect width="60" height="40" fill="#AA151B" />
      <rect y="10" width="60" height="20" fill="#F1BF00" />
    </>
  ),
  CH: (
    <>
      <rect width="60" height="40" fill="#D52B1E" />
      <rect x="26" y="9" width="8" height="22" fill="#fff" />
      <rect x="19" y="16" width="22" height="8" fill="#fff" />
    </>
  ),
};

export function Flag({ code, className }: { code: string; className?: string }) {
  const inner = FLAGS[code];
  if (!inner) return null;
  return (
    <svg viewBox="0 0 60 40" className={className} aria-hidden="true">
      {inner}
    </svg>
  );
}
