"use client";

/**
 * Auth-session helpers — cookie mode (since the httpOnly + CSRF
 * migration).
 *
 * The JWT now lives in an httpOnly cookie set by the backend. JS
 * cannot read it (that's the point — XSS can't exfiltrate it). The
 * exported `getToken/setToken/clearToken` API is preserved as a thin
 * compatibility shim so the 23 existing call sites compile without
 * change; under the hood they are no-ops. The actual credential is
 * the cookie, attached automatically by `credentials: 'include'` in
 * `lib/api.ts`.
 *
 * `setToken` historically also fanned out a change event for
 * cross-tab login sync. We keep the listener bus so layout-shell
 * code that called `onTokenChange` to re-fetch `/me` still works —
 * just trigger it with a sentinel string when login happens, and
 * `null` when logout happens.
 */

type Listener = (token: string | null) => void;
const listeners = new Set<Listener>();
const SESSION_SENTINEL = "cookie";

export function getToken(): string | null {
  // The real auth cookie is httpOnly, so JS can't observe it. We
  // return a non-null sentinel when we have *any* signal that we're
  // probably logged in (the csrf cookie is JS-readable and is set
  // alongside the auth cookie on login). The cookie disappears on
  // logout / expiry, so this stays accurate enough for UI gating.
  if (typeof document === "undefined") return null;
  return readCookie("csrf_token") ? SESSION_SENTINEL : null;
}

export function setToken(_token: string) {
  // No-op: the backend sets the httpOnly auth cookie on login.
  // We still ping listeners so UI bound to `onTokenChange` re-renders.
  listeners.forEach((l) => l(SESSION_SENTINEL));
}

export function clearToken() {
  // No-op for the cookie itself (httpOnly, server-managed). The
  // backend logout endpoint clears it via Set-Cookie. We ping
  // listeners so the shell knows the session is gone.
  listeners.forEach((l) => l(null));
}

export function onTokenChange(fn: Listener): () => void {
  listeners.add(fn);
  // Storage-event sync was the old cross-tab mechanism. Cookies
  // can't trigger storage events, so cross-tab sync is best-effort
  // (the next /me call after a tab focus will resolve).
  return () => {
    listeners.delete(fn);
  };
}

/**
 * Pre-cookie helper that decoded the JWT to check expiry. With the
 * cookie being httpOnly we no longer have the JWT in JS — we have
 * to ask the backend (`/api/auth/me`) which will 401 if expired.
 * Kept for source compatibility: returns true when we have no
 * client-side signal of a session.
 */
export function isExpired(token: string | null): boolean {
  return !token;
}

/** Read a non-httpOnly cookie value. Returns null if missing. */
export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const target = `${name}=`;
  for (const part of document.cookie.split("; ")) {
    if (part.startsWith(target)) {
      return decodeURIComponent(part.slice(target.length));
    }
  }
  return null;
}
