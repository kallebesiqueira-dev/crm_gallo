import type { MetadataRoute } from "next";

import { locales } from "@/i18n/config";

// Served at /sitemap.xml (the next-intl middleware matcher excludes dotted
// paths, so it isn't locale-redirected). The authed app lives under (app) and
// redirects to login, so only the public, indexable content routes are listed.
const BASE = "https://app.gallo-crm.com";
const PATHS = ["", "privacy", "security", "terms", "cookies"] as const;

function urlFor(locale: string, path: string): string {
  return `${BASE}/${locale}${path ? `/${path}` : ""}`;
}

export default function sitemap(): MetadataRoute.Sitemap {
  return PATHS.flatMap((path) =>
    locales.map(
      (locale): MetadataRoute.Sitemap[number] => ({
        url: urlFor(locale, path),
        changeFrequency: path === "" ? "weekly" : "monthly",
        priority: path === "" ? 1 : 0.5,
        // hreflang: tell search engines these are the 7 language variants of
        // the same page so they don't compete as duplicate content.
        alternates: {
          languages: Object.fromEntries(locales.map((l) => [l, urlFor(l, path)])),
        },
      }),
    ),
  );
}
