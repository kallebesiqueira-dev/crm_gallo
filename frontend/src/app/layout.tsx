import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
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
