"use client";

import Image from "next/image";
import Link from "next/link";
import { useLocale } from "next-intl";
import { cn } from "@/lib/utils";

/**
 * Brand mark — the FULL GALLO CRM logo lockup (shield + wordmark) used
 * everywhere: marketing header/footer, auth pages, and the app sidebar.
 *
 * Single source of truth: `public/gallo-logo.png`. Swap that file to
 * re-brand the whole app at once. Rendered height-based with `rounded-xl`
 * so the badge stays crisp and softly rounded on every surface.
 */
type LogoSize = "sm" | "md" | "lg";

const SIZE: Record<LogoSize, number> = { sm: 32, md: 42, lg: 60 };

interface LogoProps {
  size?: LogoSize;
  /** Kept for API compatibility — the full lockup is shown either way. */
  iconOnly?: boolean;
  /** When set, the whole logo becomes a Link to this destination. */
  href?: string;
  /** "/" or "/${locale}" — auto-prefixed when href starts with "/". */
  localized?: boolean;
  className?: string;
  /** Accessible label (the wordmark is baked into the image). */
  label?: string;
  /** Disable Next.js priority hint when the logo is below-the-fold. */
  priority?: boolean;
}

export function Logo({
  size = "md",
  href,
  localized = true,
  className,
  label = "GALLO CRM",
  priority = true,
}: LogoProps) {
  const locale = useLocale();
  const px = SIZE[size];

  const resolvedHref =
    href && localized && href.startsWith("/") && !href.startsWith(`/${locale}`)
      ? `/${locale}${href === "/" ? "" : href}`
      : href;

  const img = (
    <Image
      src="/gallo-logo.png"
      alt={label}
      width={256}
      height={256}
      priority={priority}
      className="w-auto select-none rounded-xl"
      style={{ height: px, width: "auto" }}
    />
  );

  if (resolvedHref) {
    return (
      <Link
        href={resolvedHref}
        className={cn("inline-flex items-center", className)}
        aria-label={label}
      >
        {img}
      </Link>
    );
  }

  return (
    <span className={cn("inline-flex items-center", className)} aria-label={label}>
      {img}
    </span>
  );
}
