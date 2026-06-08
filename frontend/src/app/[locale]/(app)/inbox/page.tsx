"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { MessageCircle, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  api,
  type Conversation,
  type ConversationMessage,
  type MessageStatus,
  type User,
  type WhatsAppAccount,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

const CONVERSATIONS_POLL_MS = 15000;
const MESSAGES_POLL_MS = 6000;

export default function InboxPage() {
  const t = useTranslations("inbox");
  const locale = useLocale();

  const [user, setUser] = useState<User | null>(null);
  const [accounts, setAccounts] = useState<WhatsAppAccount[] | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const timeFmt = useMemo(
    () => new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" }),
    [locale],
  );
  const dayFmt = useMemo(
    () => new Intl.DateTimeFormat(locale, { day: "2-digit", month: "short" }),
    [locale],
  );

  const scrollRef = useRef<HTMLDivElement>(null);

  const loadAccounts = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      setAccounts(await api.listWhatsAppAccounts(token));
    } catch {
      setAccounts([]);
    }
  }, []);

  const loadConversations = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      setConversations(await api.listConversations(token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }, []);

  const loadMessages = useCallback(async (conversationId: string) => {
    const token = getToken();
    if (!token) return;
    try {
      setMessages(await api.listMessages(token, conversationId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }, []);

  // Initial load: who am I (for admin-gating connect) + accounts + threads.
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    Promise.all([
      api.me(token).then(setUser).catch(() => {}),
      loadAccounts(),
      loadConversations(),
    ]).finally(() => setLoading(false));
  }, [loadAccounts, loadConversations]);

  // Poll the conversation list so new inbound threads / unread bumps appear.
  useEffect(() => {
    const id = setInterval(loadConversations, CONVERSATIONS_POLL_MS);
    return () => clearInterval(id);
  }, [loadConversations]);

  // When a thread is selected: load its messages, clear its unread badge,
  // and poll for new ones while it's open.
  useEffect(() => {
    if (!activeId) return;
    loadMessages(activeId);
    const token = getToken();
    if (token) {
      api.markConversationRead(token, activeId).then((conv) => {
        setConversations((prev) => prev.map((c) => (c.id === conv.id ? conv : c)));
      }).catch(() => {});
    }
    const id = setInterval(() => loadMessages(activeId), MESSAGES_POLL_MS);
    return () => clearInterval(id);
  }, [activeId, loadMessages]);

  // Keep the thread pinned to the newest message.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const activeConv = conversations.find((c) => c.id === activeId) ?? null;

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    const text = draft.trim();
    if (!token || !activeId || !text) return;
    setSending(true);
    setError(null);
    try {
      const msg = await api.sendMessage(token, activeId, text);
      setMessages((prev) => [...prev, msg]);
      setDraft("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setSending(false);
    }
  }

  function previewFor(c: Conversation): string {
    return c.last_message_preview ?? t("noMessagesYet");
  }

  function bodyFor(m: ConversationMessage): string {
    if (m.body) return m.body;
    if (m.type === "text") return "";
    return t("mediaPlaceholder", { type: t(`type.${m.type}`) });
  }

  function statusLabel(s: MessageStatus): string {
    return t(`status.${s}`);
  }

  const isAdmin = user?.role === "admin";

  if (loading) {
    return (
      <div className="grid h-[calc(100vh-8rem)] place-items-center text-sm text-muted-foreground">
        {t("loading")}
      </div>
    );
  }

  // Empty state: no WhatsApp number connected yet.
  if (accounts && accounts.length === 0) {
    return <ConnectEmptyState isAdmin={isAdmin} onConnected={loadAccounts} />;
  }

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 md:grid-cols-[20rem_1fr]">
        {/* Conversation list */}
        <Card className="flex min-h-0 flex-col overflow-hidden">
          <CardHeader className="border-b py-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("conversations")}
            </CardTitle>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 overflow-y-auto p-0">
            {conversations.length === 0 ? (
              <p className="px-4 py-8 text-center text-xs text-muted-foreground">
                {t("noConversations")}
              </p>
            ) : (
              <ul className="divide-y">
                {conversations.map((c) => {
                  const active = c.id === activeId;
                  return (
                    <li key={c.id}>
                      <button
                        type="button"
                        onClick={() => setActiveId(c.id)}
                        className={cn(
                          "flex w-full items-start gap-3 px-4 py-3 text-left transition-colors",
                          active ? "bg-primary/10" : "hover:bg-accent",
                        )}
                      >
                        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                          <MessageCircle className="h-4 w-4" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center justify-between gap-2">
                            <span className="truncate text-sm font-medium">
                              {c.contact_name ?? c.contact_wa_id}
                            </span>
                            {c.last_message_at && (
                              <span className="shrink-0 text-[10px] text-muted-foreground">
                                {dayFmt.format(new Date(c.last_message_at))}
                              </span>
                            )}
                          </span>
                          <span className="mt-0.5 flex items-center justify-between gap-2">
                            <span className="truncate text-xs text-muted-foreground">
                              {previewFor(c)}
                            </span>
                            {c.unread_count > 0 && !active && (
                              <span className="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-emerald-500 px-1 text-[10px] font-semibold text-white">
                                {c.unread_count}
                              </span>
                            )}
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Thread */}
        <Card className="flex min-h-0 flex-col overflow-hidden">
          {!activeConv ? (
            <div className="grid flex-1 place-items-center p-8 text-center">
              <div className="space-y-2">
                <MessageCircle className="mx-auto h-10 w-10 text-muted-foreground/40" />
                <p className="text-sm font-medium">{t("selectConversation")}</p>
                <p className="text-xs text-muted-foreground">{t("selectConversationBody")}</p>
              </div>
            </div>
          ) : (
            <>
              <CardHeader className="border-b py-3">
                <CardTitle className="text-sm font-medium">
                  {activeConv.contact_name ?? activeConv.contact_wa_id}
                  <span className="ml-2 font-normal text-muted-foreground">
                    {activeConv.contact_wa_id}
                  </span>
                </CardTitle>
              </CardHeader>

              <div ref={scrollRef} className="min-h-0 flex-1 space-y-2 overflow-y-auto bg-muted/30 p-4">
                {messages.length === 0 ? (
                  <p className="py-8 text-center text-xs text-muted-foreground">
                    {t("noMessagesYet")}
                  </p>
                ) : (
                  messages.map((m) => {
                    const out = m.direction === "outbound";
                    return (
                      <div
                        key={m.id}
                        className={cn("flex", out ? "justify-end" : "justify-start")}
                      >
                        <div
                          className={cn(
                            "max-w-[75%] rounded-2xl px-3 py-2 text-sm shadow-sm",
                            out
                              ? "rounded-br-sm bg-emerald-500 text-white"
                              : "rounded-bl-sm bg-card",
                          )}
                        >
                          <p className="whitespace-pre-wrap break-words">{bodyFor(m)}</p>
                          <p
                            className={cn(
                              "mt-1 flex items-center justify-end gap-1 text-[10px]",
                              out ? "text-white/70" : "text-muted-foreground",
                            )}
                          >
                            <span>{timeFmt.format(new Date(m.timestamp))}</span>
                            {out && (
                              <span className={cn(m.status === "failed" && "text-rose-200")}>
                                · {statusLabel(m.status)}
                              </span>
                            )}
                          </p>
                          {out && m.status === "failed" && m.error && (
                            <p className="mt-0.5 text-[10px] text-rose-100">{m.error}</p>
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              <form onSubmit={handleSend} className="flex items-center gap-2 border-t p-3">
                <Input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder={t("messagePlaceholder")}
                  maxLength={4096}
                  aria-label={t("messagePlaceholder")}
                />
                <Button type="submit" disabled={sending || !draft.trim()} aria-label={t("send")}>
                  <Send className="h-4 w-4" />
                </Button>
              </form>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

function ConnectEmptyState({
  isAdmin,
  onConnected,
}: {
  isAdmin: boolean;
  onConnected: () => void;
}) {
  const t = useTranslations("inbox");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [displayPhone, setDisplayPhone] = useState("");
  const [verifiedName, setVerifiedName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    if (!token || !phoneNumberId.trim() || !accessToken.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.connectWhatsAppAccount(token, {
        phone_number_id: phoneNumberId.trim(),
        access_token: accessToken.trim(),
        display_phone_number: displayPhone.trim() || null,
        verified_name: verifiedName.trim() || null,
      });
      onConnected();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      <Card className="mx-auto max-w-xl">
        <CardHeader className="items-center text-center">
          <span className="mb-2 grid h-12 w-12 place-items-center rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
            <MessageCircle className="h-6 w-6" />
          </span>
          <CardTitle>{t("noAccounts")}</CardTitle>
          <p className="text-sm text-muted-foreground">{t("noAccountsBody")}</p>
        </CardHeader>
        <CardContent>
          {!isAdmin ? (
            <p className="rounded-md border bg-muted/40 px-3 py-2 text-center text-sm text-muted-foreground">
              {t("adminOnly")}
            </p>
          ) : (
            <form onSubmit={handleConnect} className="space-y-4">
              {error && (
                <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {error}
                </div>
              )}
              <div className="space-y-1">
                <Label htmlFor="wa-pnid">{t("phoneNumberId")}</Label>
                <Input
                  id="wa-pnid"
                  value={phoneNumberId}
                  onChange={(e) => setPhoneNumberId(e.target.value)}
                  placeholder="123456789012345"
                  required
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="wa-token">{t("accessToken")}</Label>
                <Input
                  id="wa-token"
                  type="password"
                  value={accessToken}
                  onChange={(e) => setAccessToken(e.target.value)}
                  placeholder="EAAG…"
                  required
                />
                <p className="text-xs text-muted-foreground">{t("accessTokenHint")}</p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="wa-phone">{t("displayPhone")}</Label>
                  <Input
                    id="wa-phone"
                    value={displayPhone}
                    onChange={(e) => setDisplayPhone(e.target.value)}
                    placeholder="+55 11 98888-7777"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="wa-name">{t("displayName")}</Label>
                  <Input
                    id="wa-name"
                    value={verifiedName}
                    onChange={(e) => setVerifiedName(e.target.value)}
                    placeholder={t("displayNamePlaceholder")}
                  />
                </div>
              </div>
              <Button type="submit" disabled={busy || !phoneNumberId.trim() || !accessToken.trim()}>
                {busy ? t("connecting") : t("connect")}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
