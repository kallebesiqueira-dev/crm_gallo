import type { MetadataRoute } from "next";

// Served at /robots.txt (excluded from the next-intl middleware by the dotted
// matcher). Allow the public marketing + legal pages; keep crawlers out of the
// API. The authed app pages redirect to login, so they expose nothing, but the
// sitemap intentionally lists only the indexable content routes.
const BASE = "https://app.gallo-crm.com";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/", disallow: "/api/" },
    sitemap: `${BASE}/sitemap.xml`,
  };
}
