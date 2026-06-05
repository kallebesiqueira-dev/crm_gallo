"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Copy, Loader2, ShieldCheck, ShieldOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { api, type MfaSetup, type MfaStatus } from "@/lib/api";

/**
 * Two-factor authentication management card.
 *
 * Three states:
 *   - DISABLED         : "Enable 2FA" button → /mfa/setup → enroll form
 *   - ENROLLING (setup is non-null) : QR (manual secret) + first-code form
 *                                     → /mfa/enable on success → backup codes
 *   - ENABLED          : status + "View backup codes count" + "Disable"
 *                        form requires password + a current code.
 *
 * Backup codes are returned ONCE by /mfa/enable. We show them inline
 * with a download/copy affordance and warn they won't be shown again.
 */
export function MfaCard({ onEnabled }: { onEnabled?: () => void } = {}) {
  const t = useTranslations("mfa");
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Enroll flow
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [enrollCode, setEnrollCode] = useState("");
  const [enrollBusy, setEnrollBusy] = useState(false);
  const [enrollError, setEnrollError] = useState<string | null>(null);

  // Backup codes — shown only immediately after enable.
  const [freshBackupCodes, setFreshBackupCodes] = useState<string[] | null>(null);
  const [copied, setCopied] = useState(false);

  // Disable flow
  const [disablePassword, setDisablePassword] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [disableBusy, setDisableBusy] = useState(false);
  const [disableError, setDisableError] = useState<string | null>(null);

  async function refresh() {
    try {
      setStatus(await api.mfaStatus());
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Load failed");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function startSetup() {
    setEnrollError(null);
    try {
      setSetup(await api.mfaSetup());
      setEnrollCode("");
    } catch (e) {
      setEnrollError(e instanceof Error ? e.message : "Setup failed");
    }
  }

  async function confirmEnable(e: React.FormEvent) {
    e.preventDefault();
    setEnrollBusy(true);
    setEnrollError(null);
    try {
      const res = await api.mfaEnable(enrollCode.trim());
      setFreshBackupCodes(res.backup_codes);
      setSetup(null);
      setEnrollCode("");
      await refresh();
      onEnabled?.();
    } catch (err) {
      setEnrollError(err instanceof Error ? err.message : "Invalid code");
    } finally {
      setEnrollBusy(false);
    }
  }

  async function confirmDisable(e: React.FormEvent) {
    e.preventDefault();
    setDisableBusy(true);
    setDisableError(null);
    try {
      await api.mfaDisable(disablePassword, disableCode.trim());
      setDisablePassword("");
      setDisableCode("");
      setFreshBackupCodes(null);
      await refresh();
    } catch (err) {
      setDisableError(err instanceof Error ? err.message : "Disable failed");
    } finally {
      setDisableBusy(false);
    }
  }

  async function copyCodes() {
    if (!freshBackupCodes) return;
    try {
      await navigator.clipboard.writeText(freshBackupCodes.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard may be blocked — codes are still visible on screen */
    }
  }

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {status?.enabled ? (
            <ShieldCheck className="h-4 w-4 text-emerald-500" />
          ) : (
            <ShieldOff className="h-4 w-4 text-muted-foreground" />
          )}
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {loadError && <p className="text-sm text-destructive">{loadError}</p>}

        {/* Fresh backup codes — render at the top so they can't be
            scrolled past by accident. */}
        {freshBackupCodes && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-4 text-sm">
            <div className="mb-2 font-semibold text-amber-700 dark:text-amber-300">
              {t("backupCodesTitle")}
            </div>
            <p className="mb-3 text-xs text-amber-700/90 dark:text-amber-200/90">
              {t("backupCodesWarning")}
            </p>
            <pre className="overflow-x-auto rounded bg-background/80 p-3 font-mono text-xs">
              {freshBackupCodes.join("\n")}
            </pre>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={copyCodes}
            >
              <Copy className="h-3 w-3" />
              {copied ? t("copied") : t("copy")}
            </Button>
          </div>
        )}

        {status === null ? (
          <div className="grid place-items-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : status.enabled ? (
          <DisableSection
            password={disablePassword}
            setPassword={setDisablePassword}
            code={disableCode}
            setCode={setDisableCode}
            busy={disableBusy}
            error={disableError}
            onSubmit={confirmDisable}
            backupCodesRemaining={status.backup_codes_remaining}
          />
        ) : setup ? (
          <EnrollSection
            setup={setup}
            code={enrollCode}
            setCode={setEnrollCode}
            busy={enrollBusy}
            error={enrollError}
            onSubmit={confirmEnable}
            onCancel={() => {
              setSetup(null);
              setEnrollCode("");
              setEnrollError(null);
            }}
          />
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{t("disabledBody")}</p>
            <Button onClick={startSetup}>{t("enableButton")}</Button>
            {enrollError && (
              <p className="text-sm text-destructive">{enrollError}</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function EnrollSection(props: {
  setup: MfaSetup;
  code: string;
  setCode: (v: string) => void;
  busy: boolean;
  error: string | null;
  onSubmit: (e: React.FormEvent) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("mfa");
  // We don't ship a QR rendering library — instead we use the
  // openly-hosted Google Chart API to render the otpauth:// URI as a
  // PNG QR. Acceptable in dev; production should swap for a
  // client-side renderer (e.g. `qrcode.react`) to avoid third-party
  // requests during enrollment.
  const qrSrc = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(props.setup.provisioning_uri)}`;
  return (
    <form onSubmit={props.onSubmit} className="space-y-4">
      <div className="grid gap-4 md:grid-cols-[200px_1fr]">
        <img
          src={qrSrc}
          alt="MFA QR code"
          width={200}
          height={200}
          className="rounded-md border bg-white p-2"
        />
        <div className="space-y-2 text-sm">
          <p className="text-muted-foreground">{t("enrollScanHint")}</p>
          <div>
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">
              {t("enrollManualKey")}
            </Label>
            <code className="mt-1 block break-all rounded bg-muted px-2 py-1 font-mono text-xs">
              {props.setup.secret}
            </code>
          </div>
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor="enroll_code">{t("enrollCodeLabel")}</Label>
        <Input
          id="enroll_code"
          autoComplete="one-time-code"
          inputMode="numeric"
          pattern="[0-9]{6}"
          maxLength={6}
          required
          value={props.code}
          onChange={(e) => props.setCode(e.target.value)}
          placeholder="123456"
        />
      </div>
      {props.error && <p className="text-sm text-destructive">{props.error}</p>}
      <div className="flex gap-2">
        <Button type="submit" disabled={props.busy}>
          {props.busy ? t("enrolling") : t("enrollConfirm")}
        </Button>
        <Button type="button" variant="ghost" onClick={props.onCancel}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}

function DisableSection(props: {
  password: string;
  setPassword: (v: string) => void;
  code: string;
  setCode: (v: string) => void;
  busy: boolean;
  error: string | null;
  onSubmit: (e: React.FormEvent) => void;
  backupCodesRemaining: number;
}) {
  const t = useTranslations("mfa");
  return (
    <form onSubmit={props.onSubmit} className="space-y-4">
      <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm">
        <p className="font-medium text-emerald-700 dark:text-emerald-300">
          {t("enabledBanner")}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {t("backupCodesRemaining", { count: props.backupCodesRemaining })}
        </p>
      </div>
      <p className="text-sm text-muted-foreground">{t("disableHint")}</p>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="disable_password">{t("currentPassword")}</Label>
          <PasswordInput
            id="disable_password"
            autoComplete="current-password"
            required
            value={props.password}
            onChange={(e) => props.setPassword(e.target.value)}
            visibilityLabels={{ show: t("showPassword"), hide: t("hidePassword") }}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="disable_code">{t("currentCode")}</Label>
          <Input
            id="disable_code"
            autoComplete="one-time-code"
            inputMode="text"
            required
            value={props.code}
            onChange={(e) => props.setCode(e.target.value)}
            placeholder="123456 or backup-code"
          />
        </div>
      </div>
      {props.error && <p className="text-sm text-destructive">{props.error}</p>}
      <Button type="submit" variant="destructive" disabled={props.busy}>
        {props.busy ? t("disabling") : t("disableButton")}
      </Button>
    </form>
  );
}
