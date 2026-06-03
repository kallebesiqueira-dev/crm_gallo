"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Check, Copy, Loader2, Plus, Send, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useConfirm } from "@/components/confirm-dialog";
import { api, type SignatureRequest, type SignatureStatus } from "@/lib/api";
import { getToken } from "@/lib/auth";

const STATUS_VARIANT: Record<SignatureStatus, BadgeProps["variant"]> = {
  drafted: "outline",
  sent: "secondary",
  viewed: "warning",
  signed: "success",
  countersigned: "success",
  declined: "danger",
  cancelled: "outline",
};

// A request can still be acted on by the owner while it's pre-terminal.
const CANCELLABLE: SignatureStatus[] = ["drafted", "sent", "viewed"];

export function SignaturePanel({
  quoteId,
  quoteStatus,
}: {
  quoteId: string;
  quoteStatus: string;
}) {
  const t = useTranslations("signatures");
  const tCommon = useTranslations("common");
  const confirm = useConfirm();

  const [requests, setRequests] = useState<SignatureRequest[]>([]);
  const [creating, setCreating] = useState(false);
  const [signerName, setSignerName] = useState("");
  const [signerEmail, setSignerEmail] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      const page = await api.listSignatureRequests(token, quoteId);
      setRequests(page.items);
    } catch {
      /* non-fatal — panel just stays empty */
    }
  }, [quoteId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await api.createSignatureRequest(token, {
        quote_id: quoteId,
        signer_name: signerName.trim(),
        signer_email: signerEmail.trim(),
        message: message.trim() || null,
      });
      setSignerName("");
      setSignerEmail("");
      setMessage("");
      setCreating(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleSend(id: string) {
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const sent = await api.sendSignatureRequest(token, id);
      await load();
      if (sent.signing_url) await copyLink(sent.signing_url, id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function copyLink(url: string, id: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopiedId(id);
      setTimeout(() => setCopiedId((c) => (c === id ? null : c)), 2000);
    } catch {
      /* clipboard blocked — ignore */
    }
  }

  async function handleCopy(id: string) {
    const token = getToken();
    if (!token) return;
    // The list payload omits signing_url; the single GET rebuilds it
    // from the token, so fetch on demand.
    try {
      const fresh = await api.getSignatureRequest(token, id);
      if (fresh.signing_url) await copyLink(fresh.signing_url, id);
    } catch {
      /* ignore */
    }
  }

  async function handleCancel(id: string) {
    const ok = await confirm({
      title: t("confirmCancel"),
      tone: "danger",
      confirmLabel: t("cancelRequest"),
    });
    if (!ok) return;
    const token = getToken();
    if (!token) return;
    setBusy(true);
    try {
      await api.cancelSignatureRequest(token, id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  const canRequest = quoteStatus === "sent";

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{t("panelTitle")}</CardTitle>
          {canRequest && !creating && (
            <Button size="sm" variant="outline" onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" />
              {t("request")}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && <p className="text-sm text-destructive">{error}</p>}

        {!canRequest && requests.length === 0 && (
          <p className="text-sm text-muted-foreground">{t("requestOnlyWhenSent")}</p>
        )}

        {creating && (
          <form onSubmit={handleCreate} className="space-y-3 rounded-md border p-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="signerName">{t("signerName")}</Label>
                <Input
                  id="signerName"
                  value={signerName}
                  onChange={(e) => setSignerName(e.target.value)}
                  placeholder={t("signerNamePlaceholder")}
                  required
                  autoFocus
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="signerEmail">{t("signerEmail")}</Label>
                <Input
                  id="signerEmail"
                  type="email"
                  value={signerEmail}
                  onChange={(e) => setSignerEmail(e.target.value)}
                  placeholder={t("signerEmailPlaceholder")}
                  required
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="message">{t("message")}</Label>
              <Input
                id="message"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder={t("messagePlaceholder")}
              />
            </div>
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={busy}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : t("createRequest")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => setCreating(false)}
              >
                {tCommon("cancel")}
              </Button>
            </div>
          </form>
        )}

        {requests.length === 0 && !creating ? (
          canRequest && <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {requests.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{r.signer_name}</p>
                  <p className="truncate text-xs text-muted-foreground">{r.signer_email}</p>
                </div>
                <Badge variant={STATUS_VARIANT[r.status]}>{t(`statuses.${r.status}`)}</Badge>
                <div className="flex items-center gap-1">
                  {r.status === "drafted" && (
                    <Button size="sm" disabled={busy} onClick={() => handleSend(r.id)}>
                      <Send className="h-3.5 w-3.5" />
                      {t("sendForSigning")}
                    </Button>
                  )}
                  {(r.status === "sent" || r.status === "viewed") && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() => handleCopy(r.id)}
                    >
                      {copiedId === r.id ? (
                        <Check className="h-3.5 w-3.5" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                      {copiedId === r.id ? t("copied") : t("copyLink")}
                    </Button>
                  )}
                  {CANCELLABLE.includes(r.status) && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => handleCancel(r.id)}
                      aria-label={t("cancelRequest")}
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
