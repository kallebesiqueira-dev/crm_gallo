"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Copy, Loader2, ShieldAlert, Trash2, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { api, type Invite, type Role } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

/**
 * Team management card — list pending invites + invite-someone form +
 * revoke button. Lives on /settings (current iteration); will move to
 * a dedicated /team page once we have more team-mgmt surface
 * (membership list, role changes, remove member).
 *
 * Visible to all roles but mutations gated server-side: the admin-only
 * 403 surfaces inline if a non-admin tries to invite. We could hide the
 * form for non-admins, but the role check happens on the dep stack so
 * the API is the source of truth — UI gating is a UX nicety, not a
 * security boundary.
 */
const ROLE_OPTIONS: Role[] = ["admin", "manager", "sales_agent", "support_agent"];

export function TeamCard({ canInvite }: { canInvite: boolean }) {
  const t = useTranslations("team");
  const [invites, setInvites] = useState<Invite[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("sales_agent");
  const [busy, setBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [lastUrl, setLastUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const reload = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      setInvites(await api.listInvites(token));
      setLoadError(null);
    } catch (e) {
      // 403 means non-admin → just hide the list, no scary error.
      if (e instanceof Error && e.message.includes("admin")) {
        setInvites([]);
      } else {
        setLoadError(e instanceof Error ? e.message : "Load failed");
      }
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setCreateError(null);
    setLastUrl(null);
    try {
      const invite = await api.createInvite(token, email.trim(), role);
      setEmail("");
      setLastUrl(invite.invite_url ?? null);
      await reload();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(invite: Invite) {
    const token = getToken();
    if (!token) return;
    if (!confirm(t("confirmRevoke", { email: invite.email }))) return;
    try {
      await api.revokeInvite(token, invite.id);
      await reload();
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : "Revoke failed");
    }
  }

  async function copyUrl(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked by browser permissions — user can copy manually */
    }
  }

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserPlus className="h-4 w-4" />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Invite form — disabled for non-admins, but kept visible so they
            know the feature exists and who can use it. */}
        {canInvite ? (
          <form onSubmit={handleCreate} className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
              <div className="space-y-1.5">
                <Label htmlFor="invite_email">{t("emailLabel")}</Label>
                <Input
                  id="invite_email"
                  type="email"
                  required
                  placeholder="teammate@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="invite_role">{t("roleLabel")}</Label>
                <Select
                  id="invite_role"
                  aria-label={t("roleLabel")}
                  value={role}
                  onChange={(e) => setRole(e.target.value as Role)}
                >
                  {ROLE_OPTIONS.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="self-end">
                <Button type="submit" disabled={busy || !email.trim()}>
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : t("sendInvite")}
                </Button>
              </div>
            </div>
            {createError && (
              <p className="text-sm text-destructive">{createError}</p>
            )}
            {lastUrl && (
              <div className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">
                <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-primary">
                  {t("inviteCreated")}
                </div>
                <div className="flex items-center gap-2">
                  <code className="flex-1 truncate font-mono text-xs">{lastUrl}</code>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => copyUrl(lastUrl)}
                    type="button"
                  >
                    <Copy className="h-3 w-3" />
                    {copied ? t("copied") : t("copy")}
                  </Button>
                </div>
                <p className="mt-1.5 text-xs text-muted-foreground">
                  {t("inviteEmailNotSent")}
                </p>
              </div>
            )}
          </form>
        ) : (
          <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-900 dark:text-amber-200">
            <ShieldAlert className="h-4 w-4" />
            {t("adminOnly")}
          </div>
        )}

        {/* Pending invites table */}
        <div>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold">{t("pendingInvites")}</h3>
            {invites && (
              <span className="text-xs text-muted-foreground">
                {invites.length} {invites.length === 1 ? t("invite") : t("invites")}
              </span>
            )}
          </div>
          {loadError ? (
            <p className="text-sm text-destructive">{loadError}</p>
          ) : invites === null ? (
            <div className="grid place-items-center py-6">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : invites.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("noPending")}</p>
          ) : (
            <ul className="divide-y rounded-md border">
              {invites.map((i) => (
                <li
                  key={i.id}
                  className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{i.email}</div>
                    <div className="text-xs text-muted-foreground">
                      {i.role} ·{" "}
                      {t("expiresAt", {
                        date: new Date(i.expires_at).toLocaleDateString(),
                      })}
                    </div>
                  </div>
                  {canInvite && (
                    <button
                      type="button"
                      onClick={() => handleRevoke(i)}
                      className={cn(
                        "rounded-md border border-transparent p-1.5 text-muted-foreground transition-colors",
                        "hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive",
                      )}
                      aria-label={t("revoke")}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
