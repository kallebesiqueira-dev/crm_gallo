import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Self-contained server bundle (.next/standalone) so the production Docker
  // image ships only the traced runtime deps — no dev toolchain, no full
  // node_modules. This is what keeps the runner stage small and Trivy-clean
  // (see frontend/Dockerfile).
  output: "standalone",
};

export default withNextIntl(nextConfig);
