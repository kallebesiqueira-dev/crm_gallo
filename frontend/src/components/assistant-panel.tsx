"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocale, useTranslations } from "next-intl";
import { Send, Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { getToken } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

interface Msg {
  role: "user" | "assistant";
  content: string;
}

/**
 * Global assistant slide-out (skills.md §4 rework): the old /assistant page
 * as a right-hand panel reachable from the top bar on ANY screen. The
 * component stays mounted (the conversation survives open/close) but the
 * DOM renders only while open — same pattern as MobileNav — so its submit
 * button never shadows page forms for generic selectors/assistive tech.
 * Portaled to body because the top bar's backdrop-blur would trap a fixed
 * descendant; sized with 100dvh so the composer clears the iOS toolbar.
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
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => setMounted(true), []);

  // Esc closes + background scroll lock while open; focus the composer.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    inputRef.current?.focus();
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    if (!token || !input.trim() || busy) return;

    const userMsg: Msg = { role: "user", content: input.trim() };
    const history = messages.map((m) => ({ role: m.role, content: m.content }));

    setMessages((prev) => [...prev, userMsg, { role: "assistant", content: "" }]);
    setInput("");
    setBusy(true);

    try {
      const res = await fetch(`${API_URL}/api/assistant/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: userMsg.content, locale, history }),
      });

      if (!res.ok || !res.body) {
        const text = await res.text().catch(() => "Network error");
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: `⚠️ ${text}` };
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
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: `⚠️ ${parsed.error}`,
                };
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

  if (!mounted || !open) return null;

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
        className="fixed inset-y-0 right-0 z-[95] flex h-[100dvh] w-full max-w-md flex-col border-l bg-card shadow-xl"
      >
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary/10 text-primary">
              <Sparkles className="h-4 w-4" />
            </span>
            <span className="text-sm font-semibold">{tNav("assistant")}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
          {messages.length === 0 && (
            <p className="text-sm text-muted-foreground">{t("empty")}</p>
          )}
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

        <form
          onSubmit={send}
          className="flex gap-2 border-t px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
        >
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t("placeholder")}
            disabled={busy}
            className="flex h-10 w-full min-w-0 rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          />
          <Button type="submit" disabled={busy || !input.trim()} className="shrink-0">
            <Send className="h-4 w-4" />
          </Button>
        </form>
      </aside>
    </>,
    document.body,
  );
}
