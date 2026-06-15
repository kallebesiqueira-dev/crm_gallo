"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocale, useTranslations } from "next-intl";
import { ArrowUp, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { getToken, readCookie } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

interface Msg {
  role: "user" | "assistant";
  content: string;
}

/**
 * Global AI assistant (skills.md §3 priority A — "Gemini in Gmail" redesign).
 * A bottom-sheet on mobile (rounded top, drag handle, dashboard visible behind
 * a soft blur) and a floating panel anchored bottom-right on desktop — never a
 * full-screen page. The empty state leads with a brand-gradient greeting; once
 * a conversation starts the messages stream in (SSE, reused as-is). Enter sends,
 * Shift+Enter adds a newline. Portaled to <body> so the top bar's backdrop-blur
 * doesn't trap the fixed sheet; sized with dvh so the composer clears the iOS
 * toolbar. Colors follow the project tokens + the dashboard brand gradient.
 */
export function AssistantPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const tNav = useTranslations("nav");
  const t = useTranslations("assistant");
  const locale = useLocale();
  const [mounted, setMounted] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => setMounted(true), []);

  // Esc closes + background scroll lock while open; focus the composer.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    setTimeout(() => inputRef.current?.focus(), 50);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  // Auto-grow the composer up to a few lines.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  }, [input]);

  async function sendText(text: string) {
    const token = getToken();
    const content = text.trim();
    if (!token || !content || busy) return;

    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content }, { role: "assistant", content: "" }]);
    setInput("");
    setBusy(true);

    try {
      // Auth is the httpOnly cookie (+ double-submit CSRF), same as lib/api.ts —
      // NOT a Bearer token (getToken() is a sentinel since the cookie migration).
      const csrf = readCookie("csrf_token");
      const res = await fetch(`${API_URL}/api/assistant/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(csrf ? { "X-CSRF-Token": csrf } : {}),
        },
        credentials: "include",
        body: JSON.stringify({ message: content, locale, history }),
      });

      if (!res.ok || !res.body) {
        const errText = await res.text().catch(() => "Network error");
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: `⚠️ ${errText}` };
          return updated;
        });
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6);
          if (raw === "[DONE]") break;
          try {
            const parsed = JSON.parse(raw) as { token?: string; error?: string };
            if (parsed.token) {
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: updated[updated.length - 1].content + parsed.token,
                };
                return updated;
              });
              bottomRef.current?.scrollIntoView({ behavior: "smooth" });
            }
            if (parsed.error) {
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: "assistant", content: `⚠️ ${parsed.error}` };
                return updated;
              });
            }
          } catch {
            // ignore malformed SSE line
          }
        }
      }
    } catch (e) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: e instanceof Error ? e.message : "Error",
        };
        return updated;
      });
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    void sendText(input);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendText(input);
    }
  }

  if (!mounted || !open) return null;

  const hasConvo = messages.length > 0;

  return createPortal(
    <>
      <div
        className="fixed inset-0 z-[94] bg-foreground/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={tNav("assistant")}
        className={cn(
          "fixed z-[95] flex flex-col border bg-card text-card-foreground shadow-2xl",
          "animate-in slide-in-from-bottom duration-200",
          // mobile: bottom-sheet
          "inset-x-0 bottom-0 max-h-[88dvh] rounded-t-2xl",
          // desktop: floating panel anchored bottom-right
          "sm:inset-x-auto sm:bottom-6 sm:right-6 sm:left-auto sm:w-[26rem] sm:max-h-[40rem] sm:rounded-2xl",
        )}
      >
        {/* drag handle (mobile only) */}
        <div className="flex justify-center pt-2 sm:hidden">
          <span className="h-1.5 w-10 rounded-full bg-muted-foreground/30" />
        </div>

        <div className="flex items-center justify-between px-4 py-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary/10 text-primary">
            <Sparkles className="h-4 w-4" />
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("close")}
            className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4">
          {!hasConvo ? (
            <div className="flex flex-col gap-2 py-6">
              <h2 className="bg-gradient-to-r from-violet-600 to-fuchsia-500 bg-clip-text text-2xl font-bold tracking-tight text-transparent dark:from-white dark:to-violet-200">
                {t("hero")}
              </h2>
              <p className="text-sm text-muted-foreground">{t("empty")}</p>
            </div>
          ) : (
            <div className="space-y-3 py-3">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={cn(
                    "max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm",
                    m.role === "user" ? "ml-auto bg-primary text-primary-foreground" : "bg-muted",
                  )}
                >
                  {m.content}
                  {busy && i === messages.length - 1 && m.role === "assistant" && !m.content && (
                    <span className="inline-block h-4 w-1 animate-pulse bg-current opacity-70" />
                  )}
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <form
          onSubmit={onSubmit}
          className="px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3"
        >
          <div className="flex items-end gap-2 rounded-2xl border border-input bg-background px-3 py-2 focus-within:ring-2 focus-within:ring-ring">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              rows={1}
              placeholder={t("placeholder")}
              disabled={busy}
              className="max-h-32 flex-1 resize-none bg-transparent text-sm outline-none placeholder:text-muted-foreground disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              aria-label={t("placeholder")}
              className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground transition hover:bg-primary/90 disabled:opacity-40"
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          </div>
          <p className="mt-2 text-center text-[11px] text-muted-foreground">{t("disclaimer")}</p>
        </form>
      </aside>
    </>,
    document.body,
  );
}
