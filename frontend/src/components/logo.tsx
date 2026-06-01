"use client";

import Image from "next/image";
import Link from "next/link";
import { useLocale } from "next-intl";
import { cn } from "@/lib/utils";

/**
 * Single source of truth for the CRM Gallo brand mark.
 *
 * - Renders at exact pixel dimensions via Next/Image (no implicit scaling),
 *   so the raster stays crisp on both Retina/HiDPI and standard Win/Mac
 *   displays. `priority` is on by default because the logo is above-the-
 *   fold on every surface that uses this component.
 * - Optional wordmark sits next to the icon. Pass `iconOnly` for compact
 *   spots (mobile burger menu, favicons-like spaces).
 * - When `href` is provided we wrap the whole thing in a Next/Link; otherwise
 *   it renders as a static <span> so it can drop into footers and dialogs
 *   without an unwanted anchor.
 *
 * Asset: `frontend/public/logo.png` — high-resolution PNG of the rooster
 * + neural-network mark. Replace the file in-place to update the brand
 * everywhere at once.
 */

type LogoSize = "sm" | "md" | "lg";

const SIZE: Record<LogoSize, { px: number; gap: string; text: string }> = {
  sm: { px: 28, gap: "gap-2", text: "text-sm" },
  md: { px: 36, gap: "gap-2.5", text: "text-base" },
  lg: { px: 48, gap: "gap-3", text: "text-lg" },
};

interface LogoProps {
  size?: LogoSize;
  /** Render only the rooster mark, no wordmark. */
  iconOnly?: boolean;
  /** When set, the whole logo becomes a Link to this destination. */
  href?: string;
  /** "/" or "/${locale}" — auto-prefixed when href starts with "/". */
  localized?: boolean;
  className?: string;
  /** Override the wordmark label (defaults to "CRM Gallo"). */
  label?: string;
  /** Disable Next.js priority hint when the logo is below-the-fold. */
  priority?: boolean;
}

export function Logo({
  size = "md",
  iconOnly = false,
  href,
  localized = true,
  className,
  label = "CRM Gallo",
  priority = true,
}: LogoProps) {
  const locale = useLocale();
  const s = SIZE[size];

  const resolvedHref =
    href && localized && href.startsWith("/") && !href.startsWith(`/${locale}`)
      ? `/${locale}${href === "/" ? "" : href}`
      : href;

  const inner = (
    <>
      <Image
        src="/logo.png"
        alt={iconOnly ? label : ""}
        width={s.px}
        height={s.px}
        priority={priority}
        // Explicit width/height + intrinsic sizing keep the bitmap pixel-
        // perfect on standard displays; Next/Image emits srcSet for 2x/3x
        // so Retina + Win HiDPI stay crisp. `rounded-full` clips the raster
        // into a disc — pairs cleanly with the gallo silhouette and reads
        // as a real brand mark instead of a bare PNG tile.
        className="h-auto w-auto select-none rounded-full"
        style={{ width: s.px, height: s.px }}
      />
      {!iconOnly && (
        <span className={cn("font-semibold tracking-tight", s.text)}>{label}</span>
      )}
    </>
  );

  const wrapperClass = cn("inline-flex items-center", s.gap, className);

  if (resolvedHref) {
    return (
      <Link href={resolvedHref} className={wrapperClass} aria-label={label}>
        {inner}
      </Link>
    );
  }

  return (
    <span className={wrapperClass} aria-label={iconOnly ? label : undefined}>
      {inner}
    </span>
  );
}
