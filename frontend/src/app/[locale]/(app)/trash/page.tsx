"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { RotateCcw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useConfirm } from "@/components/confirm-dialog";
import { api, type TrashItem } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

type Tab = "all" | TrashItem["entity_type"];

const TABS: Tab[] = ["all", "lead", "customer", "deal", "task"];

export default function TrashPage() {
  const t = useTranslations("trash");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const confirm = useConfirm();
  const [items, setItems] = useState<TrashItem[]>([]);
  const [tab, setTab] = useState<Tab>("all");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const token = getToken();
    if (!token) return;
    const list = await api.listTrash(token);
    setItems(list);
  }

  useEffect(() => {
    refresh();
  }, []);

  const filtered = useMemo(
    () => (tab === "all" ? items : items.filter((i) => i.entity_type === tab)),
    [items, tab],
  );

  async function restore(item: TrashItem) {
    const token = getToken();
    if (!token) return;
    setError(null);
    try {
      await api.restoreFromTrash(token, item.entity_type, item.id);
      setItems((prev) =>
        prev.filter((i) => !(i.id === item.id && i.entity_type === item.entity_type)),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  async function hardDelete(item: TrashItem) {
    const ok = await confirm({
      title: t("confirmHardDelete"),
      tone: "danger",
      confirmLabel: t("hardDelete"),
    });
    if (!ok) return;
    const token = getToken();
    if (!token) return;
    setError(null);
    try {
      await api.hardDelete(token, item.entity_type, item.id);
      setItems((prev) =>
        prev.filter((i) => !(i.id === item.id && i.entity_type === item.entity_type)),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  async function emptyAll() {
    if (items.length === 0) return;
    const ok = await confirm({
      title: t("confirmEmpty"),
      tone: "danger",
      confirmLabel: t("emptyAll"),
    });
    if (!ok) return;
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await api.emptyTrash(token);
      setItems([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : tCommon("noPermission"));
    } finally {
      setBusy(false);
    }
  }

  const counts: Record<Tab, number> = {
    all: items.length,
    lead: items.filter((i) => i.entity_type === "lead").length,
    customer: items.filter((i) => i.entity_type === "customer").length,
    deal: items.filter((i) => i.entity_type === "deal").length,
    task: items.filter((i) => i.entity_type === "task").length,
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        <Button
          variant="destructive"
          onClick={emptyAll}
          disabled={items.length === 0 || busy}
        >
          <Trash2 className="h-4 w-4" />
          {t("emptyAll")}
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="flex flex-wrap gap-2 border-b">
        {TABS.map((kt) => (
          <button
            key={kt}
            type="button"
            onClick={() => setTab(kt)}
            className={cn(
              "border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === kt
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t(`tabs.${kt}`)}{" "}
            <span className="ml-1 text-xs text-muted-foreground">({counts[kt]})</span>
          </button>
        ))}
      </div>

      <Card className="overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-10 text-center text-sm text-muted-foreground">{t("empty")}</div>
        ) : (
          <ul className="divide-y">
            {filtered.map((item) => (
              <li
                key={`${item.entity_type}-${item.id}`}
                className="flex items-center gap-3 px-4 py-3 hover:bg-muted/30"
              >
                <span className="rounded bg-muted px-2 py-0.5 text-xs uppercase tracking-wider text-muted-foreground">
                  {t(`tabs.${item.entity_type}`)}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{item.title}</div>
                  <div className="text-xs text-muted-foreground">
                    {t("deletedAt")}: {new Date(item.deleted_at).toLocaleString(locale)}
                  </div>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => restore(item)}
                >
                  <RotateCcw className="h-4 w-4" />
                  {t("restore")}
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  onClick={() => hardDelete(item)}
                >
                  <Trash2 className="h-4 w-4" />
                  {t("hardDelete")}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
