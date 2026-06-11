"use client";

// Floating pre-sales chatbot for the landing page. Self-contained + lazy-loaded
// (see the `dynamic(..., { ssr: false })` mount in the pricing/landing page),
// so it adds nothing to the first paint and never breaks the page if the
// backend/AI is offline — failures surface as an inline error + Retry, and the
// API itself falls back to a static professional answer (source: "fallback").
//
// Accessibility: launcher has aria-label/aria-expanded/aria-controls; the panel
// is a non-modal dialog; Esc closes and returns focus to the launcher; the
// input is labelled; Enter sends; the message log is an aria-live region.

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useLocale, useTranslations } from "next-intl";
import { Bot, RefreshCw, Send, User, X } from "lucide-react";
import { publicChatbot, type ChatSource, type ChatTurn } from "@/lib/public-api";
import { cn } from "@/lib/utils";

interface Msg {
  role: "user" | "assistant";
  content: string;
  source?: ChatSource;
}

const MAX_INPUT = 2000;
const HISTORY_TURNS = 8;

export default function LandingChatbot() {
  const t = useTranslations("chatbot");
  const locale = useLocale();

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [lastUserMsg, setLastUserMsg] = useState<string | null>(null);
  const [hovered, setHovered] = useState(false);

  const launcherRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Seed the greeting the first time the panel opens.
  useEffect(() => {
    if (open && messages.length === 0) {
      setMessages([{ role: "assistant", content: t("greeting") }]);
    }
  }, [open, messages.length, t]);

  // Focus the input when the panel opens.
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Esc closes and returns focus to the launcher.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        launcherRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Keep the latest message in view.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading, error]);

  const send = useCallback(
    async (text: string) => {
      const clean = text.trim();
      if (!clean || loading) return;

      const history: ChatTurn[] = messages
        .filter((m) => m.content)
        .slice(-HISTORY_TURNS)
        .map((m) => ({ role: m.role, content: m.content }));

      setError(false);
      setLastUserMsg(clean);
      setInput("");
      setMessages((prev) => [...prev, { role: "user", content: clean }]);
      setLoading(true);
      try {
        const reply = await publicChatbot(clean, history, locale);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: reply.message, source: reply.source },
        ]);
      } catch {
        // Backend/network down — show retry. The page stays fully usable.
        setError(true);
      } finally {
        setLoading(false);
      }
    },
    [loading, messages, locale],
  );

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void send(input);
  };

  const close = () => {
    setOpen(false);
    launcherRef.current?.focus();
  };

  const suggestions = [t("suggest1"), t("suggest2"), t("suggest3")];

  return (
    <>
      {/* Interactive robot launcher (replaces the old floating button):
          hovering the robot reveals a clickable cloud above its head; clicking
          the cloud — or the robot — opens the chat. The cloud fades out once
          the chat is closed and the pointer leaves. */}
      <div
        className="fixed bottom-4 right-4 z-50"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        {/* Cloud / speech bubble — invisible until hover (or while the chat is open). */}
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label={t("launcherLabel")}
          tabIndex={hovered || open ? 0 : -1}
          className={cn(
            "absolute bottom-full right-0 mb-3 max-w-[12rem] cursor-pointer rounded-2xl",
            "bg-white px-3 py-1.5 text-center text-xs font-semibold leading-snug text-violet-700",
            "shadow-lg ring-1 ring-violet-200 transition-all duration-300 ease-out",
            "hover:-translate-y-1 hover:scale-105 dark:bg-slate-800 dark:text-violet-200 dark:ring-violet-500/40",
            "after:absolute after:right-10 after:top-full after:border-x-[6px] after:border-t-[7px] after:border-x-transparent after:border-t-white dark:after:border-t-slate-800",
            hovered || open
              ? "pointer-events-auto translate-y-0 opacity-100"
              : "pointer-events-none translate-y-2 opacity-0",
          )}
        >
          {t("launcherLabel")}
        </button>

        {/* Robot — bigger, frameless ("solto"), the launcher itself. */}
        <button
          ref={launcherRef}
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? t("close") : t("launcherLabel")}
          aria-expanded={open}
          aria-controls="gallo-chatbot-panel"
          className="block cursor-pointer rounded-2xl transition-transform duration-200 hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 focus-visible:ring-offset-2"
        >
          <Image
            src="/roboat.png"
            alt={t("launcherLabel")}
            width={128}
            height={128}
            priority={false}
            className="h-16 w-16 animate-bob object-contain drop-shadow-[0_8px_22px_rgba(76,29,149,0.5)] sm:h-24 sm:w-24"
          />
        </button>
      </div>

      {open && (
        <div
          id="gallo-chatbot-panel"
          role="dialog"
          aria-modal="false"
          aria-label={t("title")}
          className={cn(
            "fixed bottom-24 right-4 z-50 flex flex-col overflow-hidden rounded-2xl sm:bottom-40 sm:right-5",
            "border border-border bg-background shadow-2xl",
            "h-[68vh] max-h-[600px] w-[calc(100vw-2rem)] sm:w-[380px]",
          )}
        >
          <header className="flex items-center gap-3 bg-violet-600 px-4 py-3 text-white">
            <span className="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-full bg-white/15">
              <Image
                src="/roboat.png"
                alt=""
                width={36}
                height={36}
                className="h-full w-full object-cover object-top"
              />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{t("title")}</p>
              <p className="truncate text-xs text-white/80">{t("subtitle")}</p>
            </div>
            <button
              type="button"
              onClick={close}
              aria-label={t("close")}
              className="ml-auto rounded-md p-1 transition-colors hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
            >
              <X className="h-5 w-5" />
            </button>
          </header>

          <div
            ref={scrollRef}
            className="flex-1 space-y-3 overflow-y-auto px-4 py-4"
            role="log"
            aria-live="polite"
            aria-atomic="false"
          >
            {messages.map((m, i) => (
              <div
                key={i}
                className={cn("flex gap-2", m.role === "user" ? "justify-end" : "justify-start")}
              >
                {m.role === "assistant" && (
                  <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-300">
                    <Bot className="h-4 w-4" aria-hidden="true" />
                  </span>
                )}
                <div
                  className={cn(
                    "max-w-[78%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm leading-relaxed",
                    m.role === "user"
                      ? "rounded-br-sm bg-violet-600 text-white"
                      : "rounded-bl-sm bg-muted text-foreground",
                  )}
                >
                  {m.content}
                  {m.source === "fallback" && (
                    <span className="mt-1 block text-[10px] uppercase tracking-wide opacity-60">
                      {t("fallbackNote")}
                    </span>
                  )}
                </div>
                {m.role === "user" && (
                  <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground">
                    <User className="h-4 w-4" aria-hidden="true" />
                  </span>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex gap-2">
                <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-300">
                  <Bot className="h-4 w-4" aria-hidden="true" />
                </span>
                <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm bg-muted px-3.5 py-3" aria-hidden="true">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.2s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.1s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60" />
                </div>
                <span className="sr-only">{t("sending")}</span>
              </div>
            )}

            {error && (
              <div
                role="alert"
                className="flex flex-col items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              >
                <span>{t("error")}</span>
                <button
                  type="button"
                  onClick={() => lastUserMsg && void send(lastUserMsg)}
                  className="inline-flex items-center gap-1 font-medium underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive/40"
                >
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> {t("retry")}
                </button>
              </div>
            )}

            {messages.length <= 1 && !loading && !error && (
              <div className="flex flex-wrap gap-2 pt-1">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => void send(s)}
                    className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1.5 text-xs font-medium text-violet-700 transition-colors hover:bg-violet-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-300"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>

          <form onSubmit={onSubmit} className="border-t border-border p-3">
            <div className="flex items-end gap-2">
              <label htmlFor="gallo-chatbot-input" className="sr-only">
                {t("placeholder")}
              </label>
              <textarea
                id="gallo-chatbot-input"
                ref={inputRef}
                rows={1}
                value={input}
                maxLength={MAX_INPUT}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send(input);
                  }
                }}
                placeholder={t("placeholder")}
                className="max-h-28 flex-1 resize-none rounded-xl border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                aria-label={t("send")}
                className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-violet-600 text-white transition-colors hover:bg-violet-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 focus-visible:ring-offset-2 disabled:opacity-40"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
            <p className="mt-1.5 px-1 text-[10px] text-muted-foreground">{t("disclaimer")}</p>
          </form>
        </div>
      )}
    </>
  );
}
