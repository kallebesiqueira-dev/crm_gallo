"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

/**
 * Root-level fallback: catches errors thrown by the root layout itself, where
 * even the `[locale]` layout and its i18n provider are unavailable. It must
 * render its own <html>/<body> and cannot use next-intl, so the copy is a
 * minimal, hardcoded-English last resort. Inline styles because the app CSS
 * (imported by the bypassed root layout) may not be present here.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100dvh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "system-ui, -apple-system, sans-serif",
          background: "#0a0612",
          color: "#e5e7eb",
          padding: "1.5rem",
        }}
      >
        <div style={{ maxWidth: "28rem", textAlign: "center" }}>
          <h1 style={{ fontSize: "1.25rem", fontWeight: 600, margin: "0 0 0.5rem" }}>
            Something went wrong
          </h1>
          <p style={{ fontSize: "0.875rem", color: "#9ca3af", margin: "0 0 1.25rem" }}>
            An unexpected error occurred. Please try again.
          </p>
          <button
            type="button"
            onClick={() => reset()}
            style={{
              cursor: "pointer",
              border: "none",
              borderRadius: "0.375rem",
              padding: "0.5rem 1rem",
              fontSize: "0.875rem",
              fontWeight: 500,
              background: "#7c3aed",
              color: "#fff",
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
