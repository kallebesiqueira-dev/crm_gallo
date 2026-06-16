import "./globals.css";
import type { Metadata, Viewport } from "next";

// `viewport-fit=cover` lets the app paint edge-to-edge under the iOS notch /
// home indicator AND makes `env(safe-area-inset-*)` resolve to real values
// (they're 0 without it) — used by the app header (top) and main (bottom) so
// content is never clipped by the status bar or the Safari bottom bar.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export const metadata: Metadata = {
  // Absolute base so OpenGraph/canonical/sitemap-relative URLs resolve to the
  // production host instead of localhost (Next warns + emits bad OG URLs otherwise).
  metadataBase: new URL("https://app.gallo-crm.com"),
  title: "GALLO CRM",
  description: "AI-powered multilingual CRM",
  // Favicon lives in /public (has an extension) so the next-intl middleware
  // matcher excludes it — the App Router `app/icon.png` convention serves at
  // `/icon` (no extension), which the middleware would 307-redirect to add a
  // locale, breaking the icon.
  icons: {
    icon: "/icon.png",
    shortcut: "/icon.png",
    apple: "/icon.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
