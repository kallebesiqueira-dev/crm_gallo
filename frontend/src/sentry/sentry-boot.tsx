"use client";

import { useEffect } from "react";
import { initSentry } from "./init";

/**
 * Tiny client component whose only job is to fire `initSentry()`
 * once on mount. Rendered from the locale layout so every page
 * gets the SDK ready before user interaction (if `NEXT_PUBLIC_SENTRY_DSN`
 * is set; no-op otherwise). Returns no DOM.
 */
export function SentryBoot() {
  useEffect(() => {
    initSentry();
  }, []);
  return null;
}
