"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

/**
 * GDPR & data-retention settings (plan.md §5). Admin-only — the
 * backend gates GET/PATCH /api/gdpr/settings with require_roles, this
 * card just mirrors that with a friendly notice. Retention: leads
 * idle for N months are anonymized by the daily worker sweep through
 * the same erasure path as the per-record "forget" action; empty =
 * retention off (the default).
 */
export function GdprCard({ canManage }: { canManage: boolean }) {
  const t = useTranslations("gdpr");
  const tCommon = useTranslations("common");
  const [months, setMonths] = useState<string>("");
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!canManage) return;
    api
      .getGdprSettings()
      .then((s) => setMonths(s.retention_months == null ? "" : String(s.retention_months)))
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, [canManage]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      const value = months.trim() === "" ? null : Number(months);
      const updated = await api.updateGdprSettings({ retention_months: value });
      setMonths(updated.retention_months == null ? "" : String(updated.retention_months));
      setMsg(tCommon("saved"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4" aria-hidden />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!canManage ? (
          <p className="text-sm text-muted-foreground">{t("adminOnly")}</p>
        ) : !loaded ? (
          <p className="text-sm text-muted-foreground">{tCommon("loading")}</p>
        ) : (
          <form onSubmit={save} className="space-y-4">
            <p className="text-sm text-muted-foreground">{t("description")}</p>
            <div className="space-y-2">
              <Label htmlFor="gdpr-retention">{t("retentionLabel")}</Label>
              <Input
                id="gdpr-retention"
                type="number"
                min={1}
                max={120}
                placeholder={t("off")}
                value={months}
                onChange={(e) => setMonths(e.target.value)}
                className="max-w-40"
              />
              <p className="text-xs text-muted-foreground">{t("retentionHint")}</p>
            </div>
            {msg && <p className="text-sm text-emerald-600">{msg}</p>}
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={busy}>
              {t("save")}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
