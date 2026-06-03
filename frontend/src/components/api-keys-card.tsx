"use client";

import { useEffect, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";
import { Check, Copy, KeyRound, Loader2, Plus, ShieldAlert, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type ApiKey, type ApiKeyCreated, type ApiKeyScope } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

/**
 * Admin-only Public-API key manager on /settings.
 *
 * Keys are the bearer credential for `/api/v1`. The plaintext token is
 * shown EXACTLY once — on create — then only the non-secret
 * `display_prefix` is ever exposed, so the freshly-minted token is held
 * in component state until the admin dismisses it. Revoke is soft: the
 * key stays listed (greyed out) so its audit trail survives.
 */
interface Props {
  canManage: boolean;
}

interface Draft {
  name: string;
  write: boolean;
  expires_at: string;
}

const EMPTY: Draft = { name: "", write: false, expires_at: "" };

export function ApiKeysCard({ canManage }: Props) {
  const t = useTranslations("apiKeys");
  const format = useFormatter();
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const token = getToken();
    if (!token) return;
    try {
      setKeys(await api.listApiKeys(token));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startCreate() {
    setError(null);
    setCreated(null);
    setDraft({ ...EMPTY });
  }

  async function save() {
    if (!draft || !draft.name.trim()) return;
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const scopes: ApiKeyScope[] = draft.write ? ["read", "write"] : ["read"];
      const result = await api.createApiKey(token, {
        name: draft.name.trim(),
        scopes,
        expires_at: draft.expires_at ? new Date(draft.expires_at).toISOString() : null,
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

  async function copyToken() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable — the token is still selectable in the field */
    }
  }

  async function revoke(key: ApiKey) {
    if (!confirm(t("confirmRevoke", { name: key.name }))) return;
    const token = getToken();
    if (!token) return;
    setError(null);
    try {
      await api.revokeApiKey(token, key.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Revoke failed");
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
            <KeyRound className="h-4 w-4" />
            {t("title")}
          </CardTitle>
          {canManage && !draft && (
            <Button size="sm" onClick={startCreate}>
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

        {/* The minted token — shown once. Stays until dismissed. */}
        {created && (
          <div className="space-y-2 rounded-md border border-emerald-500/40 bg-emerald-500/5 p-3">
            <p className="text-sm font-medium text-emerald-800 dark:text-emerald-200">
              {t("secretOnce")}
            </p>
            <div className="flex items-center gap-2">
              <Input
                readOnly
                value={created.token}
                onFocus={(e) => e.currentTarget.select()}
                className="font-mono text-xs"
              />
              <Button size="sm" variant="outline" onClick={copyToken}>
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
              <Label htmlFor="key-name">{t("nameLabel")}</Label>
              <Input
                id="key-name"
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                placeholder={t("namePlaceholder")}
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.write}
                onChange={(e) => setDraft({ ...draft, write: e.target.checked })}
              />
              {t("allowWrite")}
            </label>
            <p className="text-xs text-muted-foreground">{t("scopesHint")}</p>
            <div className="space-y-1.5">
              <Label htmlFor="key-expires">{t("expiresLabel")}</Label>
              <Input
                id="key-expires"
                type="date"
                value={draft.expires_at}
                onChange={(e) => setDraft({ ...draft, expires_at: e.target.value })}
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setDraft(null)}>
                {t("cancel")}
              </Button>
              <Button size="sm" onClick={save} disabled={busy || !draft.name.trim()}>
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                {t("create")}
              </Button>
            </div>
          </div>
        )}

        {keys === null ? (
          <div className="grid place-items-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : keys.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ul className="space-y-2">
            {keys.map((key) => {
              const revoked = key.revoked_at !== null;
              const expired = key.expires_at !== null && new Date(key.expires_at) < new Date();
              return (
                <li
                  key={key.id}
                  className={cn(
                    "flex items-center justify-between gap-3 rounded-md border p-3",
                    revoked && "opacity-50",
                  )}
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2 font-medium">
                      <span className="truncate">{key.name}</span>
                      {key.scopes.map((s) => (
                        <span
                          key={s}
                          className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground"
                        >
                          {t(`scope.${s}`)}
                        </span>
                      ))}
                      {revoked && (
                        <span className="shrink-0 rounded-full bg-destructive/15 px-2 py-0.5 text-xs font-medium text-destructive">
                          {t("revoked")}
                        </span>
                      )}
                      {!revoked && expired && (
                        <span className="shrink-0 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-300">
                          {t("expired")}
                        </span>
                      )}
                    </div>
                    <p className="truncate font-mono text-xs text-muted-foreground">
                      {key.display_prefix}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {key.last_used_at
                        ? t("lastUsed", { date: fmtDate(key.last_used_at)! })
                        : t("neverUsed")}
                      {key.expires_at && !revoked
                        ? ` · ${t("expiresOn", { date: fmtDate(key.expires_at)! })}`
                        : ""}
                    </p>
                  </div>
                  {canManage && !revoked && (
                    <button
                      type="button"
                      onClick={() => revoke(key)}
                      aria-label={t("revoke")}
                      className={cn(
                        "shrink-0 rounded-md border border-transparent p-1.5 text-muted-foreground transition-colors",
                        "hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive",
                      )}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
