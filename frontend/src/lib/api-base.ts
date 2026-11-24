/**
 * Public API origin.
 *
 * Unset → local backend (dev). Empty string → same-origin `/api` (the
 * Next rewrite in production). A full URL is used as-is.
 */
export function resolveApiUrl(raw: string | undefined = process.env.NEXT_PUBLIC_API_URL): string {
  if (raw === undefined) return "http://localhost:8000";
  return raw.replace(/\/$/, "");
}

export const API_URL = resolveApiUrl();
