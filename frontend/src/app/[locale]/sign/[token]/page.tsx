"use client";

import { use, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle2, FileSignature, Loader2, ShieldAlert, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthShell } from "@/components/marketing/auth-shell";
import { ApiError, api, type SignatureSignContext } from "@/lib/api";

/**
 * /[locale]/sign/[token] — the unauthenticated signer surface for the
 * manual provider. The URL token IS the credential (like an invite
 * link). Fetching the context marks the request `viewed`; the GET
 * 410s once the request is signed / declined / cancelled, which we
 * collapse into a single "no longer available" screen.
 */
interface PageProps {
  params: Promise<{ token: string }>;
}

type Phase = "loading" | "ready" | "signed" | "declined" | "gone" | "notfound";

export default function SignPage({ params }: PageProps) {
  const { token } = use(params);
  const t = useTranslations("signatures");
  const tCommon = useTranslations("common");

  const [ctx, setCtx] = useState<SignatureSignContext | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [typedName, setTypedName] = useState("");
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getSigningContext(token)
      .then((c) => {
        setCtx(c);
        setTypedName(c.signer_name);
        setPhase("ready");
      })
      .catch((e) => {
        // 410 = already signed/declined/cancelled; anything else = bad link.
        setPhase(e instanceof ApiError && e.status === 410 ? "gone" : "notfound");
      });
  }, [token]);

  async function handleSign(e: React.FormEvent) {
    e.preventDefault();
    if (!typedName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.submitSignature(token, typedName.trim());
      setPhase("signed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
      setBusy(false);
    }
  }

  async function handleDecline() {
    setBusy(true);
    setError(null);
    try {
      await api.declineSignature(token, reason.trim() || null);
      setPhase("declined");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
      setBusy(false);
    }
  }

  const money = (n: number, c: string) => `${c} ${n.toFixed(2)}`;

  if (phase === "loading") {
    return (
      <AuthShell brand={<SignBrand />}>
        <div className="grid place-items-center py-12 text-muted-foreground">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
      </AuthShell>
    );
  }

  if (phase === "gone" || phase === "notfound") {
    return (
      <AuthShell brand={<SignBrand />}>
        <div className="space-y-4 text-center">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-destructive/10 text-destructive">
            <ShieldAlert className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("sign.unavailableTitle")}</h1>
          <p className="text-sm text-muted-foreground">
            {phase === "gone" ? t("sign.alreadyDone") : t("sign.notFound")}
          </p>
        </div>
      </AuthShell>
    );
  }

  if (phase === "signed") {
    return (
      <AuthShell brand={<SignBrand />}>
        <div className="space-y-4 text-center">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-500/10 text-emerald-600">
            <CheckCircle2 className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("sign.signedTitle")}</h1>
          <p className="text-sm text-muted-foreground">{t("sign.signedBody")}</p>
        </div>
      </AuthShell>
    );
  }

  if (phase === "declined") {
    return (
      <AuthShell brand={<SignBrand />}>
        <div className="space-y-4 text-center">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-muted text-muted-foreground">
            <X className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("sign.declinedTitle")}</h1>
          <p className="text-sm text-muted-foreground">{t("sign.declinedBody")}</p>
        </div>
      </AuthShell>
    );
  }

  // phase === "ready"
  return (
    <AuthShell brand={<SignBrand />}>
      <div className="space-y-6">
        <div className="space-y-1.5">
          <p className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-medium">
            <FileSignature className="h-3 w-3 text-primary" />
            {ctx!.organization_name}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">
            {t("sign.heading", { org: ctx!.organization_name })}
          </h1>
        </div>

        <div className="rounded-lg border bg-card p-4">
          <p className="text-xs uppercase tracking-wider text-muted-foreground">
            {t("sign.quoteLabel", { number: ctx!.quote_number })}
          </p>
          <p className="mt-1 font-medium">{ctx!.quote_title}</p>
          <div className="mt-3 flex items-center justify-between border-t pt-3 text-sm">
            <span className="text-muted-foreground">{t("sign.totalLabel")}</span>
            <span className="font-semibold tabular-nums">
              {money(ctx!.quote_total, ctx!.quote_currency)}
            </span>
          </div>
        </div>

        {error && (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        {declining ? (
          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="reason">{t("sign.declineReason")}</Label>
              <Input
                id="reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder={t("sign.declineReasonPlaceholder")}
                autoFocus
              />
            </div>
            <div className="flex gap-2">
              <Button variant="outline" disabled={busy} onClick={() => setDeclining(false)}>
                {tCommon("back")}
              </Button>
              <Button variant="destructive" disabled={busy} onClick={handleDecline}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : t("sign.declineSubmit")}
              </Button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSign} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="typedName">{t("sign.typedName")}</Label>
              <Input
                id="typedName"
                value={typedName}
                onChange={(e) => setTypedName(e.target.value)}
                placeholder={t("sign.typedNamePlaceholder")}
                required
                autoFocus
              />
              <p className="text-xs text-muted-foreground">{t("sign.typedNameHint")}</p>
            </div>
            <div className="flex gap-2">
              <Button type="submit" className="flex-1" disabled={busy || !typedName.trim()}>
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <FileSignature className="h-4 w-4" />
                    {t("sign.signButton")}
                  </>
                )}
              </Button>
              <Button type="button" variant="outline" disabled={busy} onClick={() => setDeclining(true)}>
                {t("sign.declineButton")}
              </Button>
            </div>
            <p className="text-center text-xs text-muted-foreground">{t("sign.legal")}</p>
          </form>
        )}
      </div>
    </AuthShell>
  );
}

function SignBrand() {
  const t = useTranslations("signatures");
  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t("sign.brandTitle")}</h2>
      <p className="text-base text-muted-foreground">{t("sign.brandSubtitle")}</p>
    </div>
  );
}
