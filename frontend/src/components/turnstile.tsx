"use client";

import { useEffect, useRef } from "react";

const SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;
const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, opts: Record<string, unknown>) => string;
      reset: (id?: string) => void;
      remove: (id?: string) => void;
    };
  }
}

/**
 * Cloudflare Turnstile widget. Renders nothing when
 * `NEXT_PUBLIC_TURNSTILE_SITE_KEY` is unset, so the app works without CAPTCHA
 * configured. Calls `onVerify(token)` once the challenge passes and
 * `onExpire()` when the token lapses (so the parent can clear it).
 *
 * The callbacks are kept in a ref so the widget mounts once and never
 * re-renders just because the parent re-rendered with new closures.
 */
export function Turnstile({
  onVerify,
  onExpire,
  onError,
}: {
  onVerify: (token: string) => void;
  onExpire?: () => void;
  onError?: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const onVerifyRef = useRef(onVerify);
  const onExpireRef = useRef(onExpire);
  const onErrorRef = useRef(onError);
  onVerifyRef.current = onVerify;
  onExpireRef.current = onExpire;
  onErrorRef.current = onError;

  useEffect(() => {
    if (!SITE_KEY) return;
    let widgetId: string | null = null;
    let cancelled = false;

    function render() {
      if (cancelled || !ref.current || !window.turnstile || widgetId) return;
      widgetId = window.turnstile.render(ref.current, {
        sitekey: SITE_KEY,
        theme: "auto",
        callback: (token: string) => onVerifyRef.current(token),
        "expired-callback": () => onExpireRef.current?.(),
        "error-callback": () => {
          onExpireRef.current?.();
          onErrorRef.current?.();
        },
      });
    }

    if (window.turnstile) {
      render();
    } else {
      const base = SCRIPT_SRC.split("?")[0];
      const existing = document.querySelector<HTMLScriptElement>(`script[src^="${base}"]`);
      if (existing) {
        existing.addEventListener("load", render, { once: true });
      } else {
        const s = document.createElement("script");
        s.src = SCRIPT_SRC;
        s.async = true;
        s.defer = true;
        s.addEventListener("load", render, { once: true });
        document.head.appendChild(s);
      }
    }

    return () => {
      cancelled = true;
      if (widgetId && window.turnstile) {
        try {
          window.turnstile.remove(widgetId);
        } catch {
          // widget already gone — ignore
        }
      }
    };
  }, []);

  if (!SITE_KEY) return null;
  return <div ref={ref} className="flex justify-center" />;
}
