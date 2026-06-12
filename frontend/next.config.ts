import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";
import { withSentryConfig } from "@sentry/nextjs";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

// Baseline security headers applied to every route. CSP is intentionally
// omitted here: a strict policy needs per-build nonces for Next's inline
// runtime and would break the app without dedicated testing — tracked as a
// follow-up. HSTS is safe because the app is only served over HTTPS in prod.
const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Self-contained server bundle (.next/standalone) so the production Docker
  // image ships only the traced runtime deps — no dev toolchain, no full
  // node_modules. This is what keeps the runner stage small and Trivy-clean
  // (see frontend/Dockerfile).
  output: "standalone",
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

// Sentry source-map upload (observability follow-up): un-minified prod
// stack traces. Strictly inert without credentials — when
// SENTRY_AUTH_TOKEN is absent (local dev, CI) the wrapper skips the
// upload and the build behaves exactly as before. Set SENTRY_AUTH_TOKEN
// + SENTRY_ORG + SENTRY_PROJECT in the PRODUCTION build environment
// (Railway) to activate.
const sentryEnabled = !!process.env.SENTRY_AUTH_TOKEN;

export default withSentryConfig(withNextIntl(nextConfig), {
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  silent: !sentryEnabled, // no upload-skipped noise on every local build
  sourcemaps: { disable: !sentryEnabled },
  // Upload only — the runtime SDK init stays in src/sentry/init.ts,
  // dynamically imported and gated on NEXT_PUBLIC_SENTRY_DSN.
  autoInstrumentServerFunctions: false,
  widenClientFileUpload: true,
});
