"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";

const ENTITIES = ["lead", "customer", "company", "product"] as const;

export default function ExportsPage() {
  const t = useTranslations("exports");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function doExport(entity: string) {
    if (!getToken()) return;
    setBusy(entity);
    setError(null);
    try {
      const blob = await api.exportEntity(entity);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${entity}s.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {ENTITIES.map((entity) => (
          <Card key={entity} className="flex items-center justify-between gap-3 p-4">
            <div className="min-w-0">
              <div className="truncate font-medium">{t(`entity.${entity}`)}</div>
              <div className="text-xs text-muted-foreground">{t("csvFormat")}</div>
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => doExport(entity)}
              disabled={busy === entity}
              className="shrink-0 gap-1.5"
            >
              {busy === entity ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              {t("download")}
            </Button>
          </Card>
        ))}
      </div>
    </div>
  );
}
