"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import posthog from "posthog-js";
import { PostHogProvider as PHProvider } from "posthog-js/react";

const KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY;
// EU cloud by default — keeps product analytics inside the EU for GDPR, in line
// with the rest of the stack (R2 EU storage, Sentry EU). Override the region with
// NEXT_PUBLIC_POSTHOG_HOST (e.g. https://us.i.posthog.com or a self-host URL).
const HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://eu.i.posthog.com";

let booted = false;
if (typeof window !== "undefined" && KEY && !booted) {
  booted = true;
  posthog.init(KEY, {
    api_host: HOST,
    capture_pageview: false, // captured manually below on client-side route changes
    capture_pageleave: true,
    persistence: "localStorage+cookie",
  });
}

/**
 * Product analytics (PostHog). A no-op until `NEXT_PUBLIC_POSTHOG_KEY` is set at
 * build time, so the app runs identically with analytics off. EU cloud by default
 * for GDPR. SPA pageviews are captured manually on pathname changes.
 */
export function PostHogProvider({ children }: { children: React.ReactNode }) {
  if (!KEY) return <>{children}</>;
  return (
    <PHProvider client={posthog}>
      <PageView />
      {children}
    </PHProvider>
  );
}

function PageView() {
  const pathname = usePathname();
  useEffect(() => {
    if (pathname) posthog.capture("$pageview", { $current_url: window.location.href });
  }, [pathname]);
  return null;
}
