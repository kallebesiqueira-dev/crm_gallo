"use client";

import { useCallback, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Loader2, RotateCcw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useConfirm } from "@/components/confirm-dialog";
import { api, type TrashCounts, type TrashItem } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

type Tab = "all" | TrashItem["entity_type"];

const TABS: Tab[] = ["all", "lead", "customer", "deal", "task"];
const PAGE = 50;

export default function TrashPage() {
  const t = useTranslations("trash");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const confirm = useConfirm();
  // The backend list is paginated (TrashPage envelope) and mixes entity
  // types server-side, so tab filtering happens client-side on the loaded
  // window while tab badges come from /api/trash/counts (always exact).
  const [items, setItems] = useState<TrashItem[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [counts, setCounts] = useState<TrashCounts | null>(null);
  const [tab, setTab] = useState<Tab>("all");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      const [page, c] = await Promise.all([
        api.listTrash(token, { limit: PAGE }),
        api.trashCounts(token),
      ]);
      setItems(page.items);
      setHasMore(page.has_more);
      setCounts(c);
      setLoading(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function loadMore() {
    const token = getToken();
    if (!token || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await api.listTrash(token, { limit: PAGE, offset: items.length });
      setItems((prev) => [...prev, ...page.items]);
      setHasMore(page.has_more);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoadingMore(false);
    }
  }

  const filtered = tab === "all" ? items : items.filter((i) => i.entity_type === tab);

  function dropItem(item: TrashItem) {
    setItems((prev) =>
      prev.filter((i) => !(i.id === item.id && i.entity_type === item.entity_type)),
    );
    setCounts((prev) =>
      prev ? { ...prev, [item.entity_type]: Math.max(0, prev[item.entity_type] - 1) } : prev,
    );
  }

  async function restore(item: TrashItem) {
    const token = getToken();
    if (!token) return;
    setError(null);
    try {
      await api.restoreFromTrash(token, item.entity_type, item.id);
      dropItem(item);
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
      dropItem(item);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  async function emptyAll() {
    if (totalCount === 0) return;
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
      setHasMore(false);
      setCounts({ lead: 0, customer: 0, deal: 0, task: 0 });
    } catch (e) {
      setError(e instanceof Error ? e.message : tCommon("noPermission"));
    } finally {
      setBusy(false);
    }
  }

  const totalCount = counts
    ? counts.lead + counts.customer + counts.deal + counts.task
    : items.length;
  const tabCount = (kt: Tab): number =>
    kt === "all" ? totalCount : (counts ? counts[kt] : items.filter((i) => i.entity_type === kt).length);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        <Button
          variant="destructive"
          onClick={emptyAll}
          disabled={totalCount === 0 || busy}
          className="shrink-0"
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
            <span className="ml-1 text-xs text-muted-foreground">({tabCount(kt)})</span>
          </button>
        ))}
      </div>

      <Card className="overflow-hidden">
        {loading ? (
          <ul className="divide-y">
            {Array.from({ length: 6 }).map((_, i) => (
              <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
                <Skeleton className="h-5 w-16 shrink-0 rounded" />
                <div className="min-w-0 flex-1 basis-40 space-y-1.5">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-3 w-28" />
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Skeleton className="h-8 w-20" />
                  <Skeleton className="h-8 w-20" />
                </div>
              </li>
            ))}
          </ul>
        ) : filtered.length === 0 ? (
          <div className="p-10 text-center text-sm text-muted-foreground">{t("empty")}</div>
        ) : (
          <ul className="divide-y">
            {filtered.map((item) => (
              <li
                key={`${item.entity_type}-${item.id}`}
                className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 hover:bg-muted/30"
              >
                <span className="shrink-0 rounded bg-muted px-2 py-0.5 text-xs uppercase tracking-wider text-muted-foreground">
                  {t(`tabs.${item.entity_type}`)}
                </span>
                <div className="min-w-0 flex-1 basis-40">
                  <div className="truncate text-sm font-medium">{item.title}</div>
                  <div className="text-xs text-muted-foreground">
                    {t("deletedAt")}: {new Date(item.deleted_at).toLocaleString(locale)}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
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
                    <span className="sr-only sm:not-sr-only">{t("hardDelete")}</span>
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {hasMore && tab === "all" && (
        <div className="flex justify-center">
          <Button type="button" variant="outline" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? <Loader2 className="h-4 w-4 animate-spin" /> : tCommon("loadMore")}
          </Button>
        </div>
      )}
    </div>
  );
}
