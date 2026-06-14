"use client";

import { useCallback, useEffect, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";
import {
  AlertTriangle,
  Check,
  Copy,
  KeyRound,
  Loader2,
  Pause,
  Play,
  Plus,
  Send,
  ShieldAlert,
  Trash2,
  Webhook,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/toast-provider";
import {
  api,
  type WebhookDeliveryStats,
  type WebhookEndpoint,
  type WebhookEndpointCreated,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

interface Props {
  canManage: boolean;
}

interface Draft {
  url: string;
  description: string;
  events: string;
}

const EMPTY: Draft = { url: "", description: "", events: "*" };

export function WebhooksCard({ canManage }: Props) {
  const t = useTranslations("webhooks");
  const format = useFormatter();
  const toast = useToast();
  const [endpoints, setEndpoints] = useState<WebhookEndpoint[] | null>(null);
  const [stats, setStats] = useState<Record<string, WebhookDeliveryStats>>({});
  const [draft, setDraft] = useState<Draft | null>(null);
  const [created, setCreated] = useState<WebhookEndpointCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  // id of the endpoint currently running a test / rotate, to disable its row.
  const [actionId, setActionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      const eps = await api.listWebhooks(token);
      setEndpoints(eps);
      setError(null);
      // Best-effort delivery metrics per endpoint — never blocks the list.
      const pairs = await Promise.all(
        eps.map(async (ep) => {
          try {
            return [ep.id, await api.getWebhookMetrics(token, ep.id)] as const;
          } catch {
            return null;
          }
        }),
      );
      setStats(Object.fromEntries(pairs.filter((p): p is NonNullable<typeof p> => p !== null)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function save() {
    if (!draft || !draft.url.trim()) return;
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const events = draft.events.trim()
        ? draft.events.split(",").map((e) => e.trim()).filter(Boolean)
        : ["*"];
      const result = await api.createWebhook(token, {
        url: draft.url.trim(),
        description: draft.description.trim() || null,
        enabled_events: events,
      });
      setDraft(null);
      setCreated(result);
      setCopied(false);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  async function copySecret() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  }

  async function togglePause(ep: WebhookEndpoint) {
    const token = getToken();
    if (!token) return;
    try {
      await api.updateWebhook(token, ep.id, { paused: !ep.paused_at });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    }
  }

  async function runTest(ep: WebhookEndpoint) {
    const token = getToken();
    if (!token) return;
    setActionId(ep.id);
    try {
      const res = await api.testWebhook(token, ep.id);
      if (res.delivered) {
        toast(t("testOk", { code: res.response_code ?? 0, ms: res.latency_ms ?? 0 }), "success");
      } else {
        toast(t("testFail", { detail: res.error ?? String(res.response_code ?? "") }), "error");
      }
      await refresh();
    } catch (e) {
      toast(e instanceof Error ? e.message : t("testFail", { detail: "" }), "error");
    } finally {
      setActionId(null);
    }
  }

  async function rotate(ep: WebhookEndpoint) {
    if (!confirm(t("confirmRotate", { url: ep.url }))) return;
    const token = getToken();
    if (!token) return;
    setActionId(ep.id);
    setError(null);
    try {
      const result = await api.rotateWebhookSecret(token, ep.id);
      setCreated(result); // reuse the one-time secret banner
      setCopied(false);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rotate failed");
    } finally {
      setActionId(null);
    }
  }

  async function remove(ep: WebhookEndpoint) {
    if (!confirm(t("confirmDelete", { url: ep.url }))) return;
    const token = getToken();
    if (!token) return;
    setError(null);
    try {
      await api.deleteWebhook(token, ep.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  function fmtDate(iso: string | null) {
    if (!iso) return null;
    return format.dateTime(new Date(iso), { dateStyle: "medium" });
  }

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Webhook className="h-4 w-4" />
            {t("title")}
          </CardTitle>
          {canManage && !draft && (
            <Button size="sm" onClick={() => { setError(null); setCreated(null); setDraft({ ...EMPTY }); }}>
              <Plus className="h-4 w-4" />
              {t("new")}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {!canManage && (
          <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-900 dark:text-amber-200">
            <ShieldAlert className="h-4 w-4" />
            {t("adminOnly")}
          </div>
        )}

        <p className="text-xs text-muted-foreground">{t("intro")}</p>

        {error && <p className="text-sm text-destructive">{error}</p>}

        {created && (
          <div className="space-y-2 rounded-md border border-emerald-500/40 bg-emerald-500/5 p-3">
            <p className="text-sm font-medium text-emerald-800 dark:text-emerald-200">
              {t("secretOnce")}
            </p>
            <div className="flex items-center gap-2">
              <Input
                readOnly
                value={created.secret}
                onFocus={(e) => e.currentTarget.select()}
                className="font-mono text-xs"
              />
              <Button size="sm" variant="outline" onClick={copySecret}>
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? t("copied") : t("copy")}
              </Button>
            </div>
            <div className="flex justify-end">
              <Button size="sm" variant="ghost" onClick={() => setCreated(null)}>
                {t("dismiss")}
              </Button>
            </div>
          </div>
        )}

        {draft && (
          <div className="space-y-3 rounded-md border p-3">
            <div className="space-y-1.5">
              <Label htmlFor="wh-url">{t("urlLabel")}</Label>
              <Input
                id="wh-url"
                value={draft.url}
                onChange={(e) => setDraft({ ...draft, url: e.target.value })}
                placeholder="https://your-server.com/webhook"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wh-desc">{t("descLabel")}</Label>
              <Input
                id="wh-desc"
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                placeholder={t("descPlaceholder")}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wh-events">{t("eventsLabel")}</Label>
              <Input
                id="wh-events"
                value={draft.events}
                onChange={(e) => setDraft({ ...draft, events: e.target.value })}
                placeholder="* or lead.created, deal.won, ..."
              />
              <p className="text-xs text-muted-foreground">{t("eventsHint")}</p>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setDraft(null)}>
                {t("cancel")}
              </Button>
              <Button size="sm" onClick={save} disabled={busy || !draft.url.trim()}>
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                {t("create")}
              </Button>
            </div>
          </div>
        )}

        {endpoints === null ? (
          <div className="grid place-items-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : endpoints.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ul className="space-y-2">
            {endpoints.map((ep) => {
              const paused = !!ep.paused_at;
              const failing = ep.consecutive_failures > 0;
              return (
                <li
                  key={ep.id}
                  className={cn(
                    "rounded-md border p-3",
                    paused && "opacity-60",
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate font-mono text-sm">{ep.url}</span>
                        {paused && (
                          <span className="shrink-0 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-300">
                            {t("paused")}
                          </span>
                        )}
                        {failing && !paused && (
                          <span className="flex shrink-0 items-center gap-1 rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] font-medium text-red-700 dark:text-red-300">
                            <AlertTriangle className="h-3 w-3" />
                            {t("failures", { count: ep.consecutive_failures })}
                          </span>
                        )}
                      </div>
                      {ep.description && (
                        <p className="mt-0.5 text-xs text-muted-foreground">{ep.description}</p>
                      )}
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {ep.enabled_events.join(", ")}
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {ep.last_success_at
                          ? t("lastSuccess", { date: fmtDate(ep.last_success_at)! })
                          : t("neverFired")}
                      </p>
                      {stats[ep.id] && stats[ep.id].total > 0 && (
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {t("metrics", {
                            rate: Math.round((stats[ep.id].success_rate ?? 0) * 100),
                            count: stats[ep.id].total,
                            p95: stats[ep.id].p95_latency_ms ?? 0,
                          })}
                        </p>
                      )}
                    </div>
                    {canManage && (
                      <div className="flex shrink-0 items-center gap-1">
                        <button
                          type="button"
                          onClick={() => runTest(ep)}
                          disabled={actionId === ep.id}
                          aria-label={t("test")}
                          title={t("test")}
                          className="rounded-md border border-transparent p-1.5 text-muted-foreground transition-colors hover:border-border hover:bg-muted disabled:opacity-50"
                        >
                          {actionId === ep.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Send className="h-3.5 w-3.5" />
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={() => rotate(ep)}
                          disabled={actionId === ep.id}
                          aria-label={t("rotate")}
                          title={t("rotate")}
                          className="rounded-md border border-transparent p-1.5 text-muted-foreground transition-colors hover:border-border hover:bg-muted disabled:opacity-50"
                        >
                          <KeyRound className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => togglePause(ep)}
                          aria-label={paused ? t("resume") : t("pause")}
                          title={paused ? t("resume") : t("pause")}
                          className="rounded-md border border-transparent p-1.5 text-muted-foreground transition-colors hover:border-border hover:bg-muted"
                        >
                          {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
                        </button>
                        <button
                          type="button"
                          onClick={() => remove(ep)}
                          aria-label={t("delete")}
                          className="rounded-md border border-transparent p-1.5 text-muted-foreground transition-colors hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
