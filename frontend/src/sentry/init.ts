/**
 * Lazy Sentry init — gated by `NEXT_PUBLIC_SENTRY_DSN`.
 *
 * Empty DSN = no-op (skip the SDK load entirely). With a DSN set,
 * captures browser exceptions + navigation transactions. We avoid
 * the auto-instrumentation `withSentryConfig` wrapper in
 * `next.config.ts` because that path requires Sentry CLI auth at
 * build time for source-map upload, which would block CI without
 * `SENTRY_AUTH_TOKEN`. The runtime-only init below is enough for
 * v1; source-map upload is a separate hardening step.
 */
export function initSentry(): void {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;
  // Dynamic import so the SDK bytes aren't shipped to clients in
  // dev (or any deployment with the DSN empty).
  void import("@sentry/nextjs").then((Sentry) => {
    Sentry.init({
      dsn,
      environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || "development",
      // Performance traces — small sample by default so a dev DSN
      // doesn't burn quota. Bump per environment.
      tracesSampleRate: Number(
        process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? "0.1"
      ),
      // No session replay in v1 — that's a separate feature with its
      // own privacy / quota implications.
      // Sentry's BrowserClient already scrubs known credential
      // patterns; the backend `before_send` mirrors this for the
      // Python side. See backend/app/sentry_setup.py.
    });
  });
}
