"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Download, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useConfirm } from "@/components/confirm-dialog";
import { TagChipList } from "@/components/entity-tags";
import { BulkTagBar } from "@/components/bulk-tag-bar";
import { SegmentBar } from "@/components/segment-bar";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Customer, type Tag } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function CustomersPage() {
  const t = useTranslations("customers");
  const tCommon = useTranslations("common");
  const tTags = useTranslations("tags");
  const locale = useLocale();
  const confirm = useConfirm();
  const [items, setItems] = useState<Customer[]>([]);
  const [tagMap, setTagMap] = useState<Record<string, Tag[]>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTags = useCallback(async (ids: string[]) => {
    const token = getToken();
    if (!token || ids.length === 0) return;
    try {
      const rows = await api.listTagAssignments(token, "customer", ids);
      setTagMap((prev) => {
        const next = { ...prev };
        for (const row of rows) next[row.entity_id] = row.tags;
        return next;
      });
    } catch {
      /* chips are non-critical — ignore */
    }
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    const handle = setTimeout(() => {
      api
        .listCustomers(token, { q: q || undefined })
        .then((page) => {
          setItems(page.items);
          setCursor(page.next_cursor);
          setHasMore(page.has_more);
          setTagMap({});
          setLoading(false);
          setSelected(new Set());
          loadTags(page.items.map((c) => c.id));
        })
        .catch(() => {
          setItems([]);
          setCursor(null);
          setHasMore(false);
          setLoading(false);
        });
    }, 200);
    return () => clearTimeout(handle);
  }, [q, loadTags]);

  async function loadMore() {
    const token = getToken();
    if (!token || !cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await api.listCustomers(token, { q: q || undefined, cursor });
      setItems((prev) => [...prev, ...page.items]);
      setCursor(page.next_cursor);
      setHasMore(page.has_more);
      loadTags(page.items.map((c) => c.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoadingMore(false);
    }
  }

  function toggleRow(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) =>
      prev.size === items.length ? new Set() : new Set(items.map((c) => c.id)),
    );
  }

  async function handleDelete(customer: Customer) {
    const ok = await confirm({
      title: tCommon("confirmDelete"),
      tone: "danger",
      confirmLabel: tCommon("delete"),
    });
    if (!ok) return;
    const token = getToken();
    if (!token) return;
    setError(null);
    try {
      await api.deleteCustomer(token, customer.id);
      setItems((prev) => prev.filter((c) => c.id !== customer.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline">
            <a href={api.exportUrl("customer")}>
              <Download className="h-4 w-4" />
              {tCommon("exportCsv")}
            </a>
          </Button>
          <Button asChild>
            <Link href={`/${locale}/customers/new`}>
              <Plus className="h-4 w-4" />
              {t("new")}
            </Link>
          </Button>
        </div>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("search")}
          className="pl-9"
        />
      </div>

      <SegmentBar
        entityType="customer"
        currentFilters={{ q }}
        onApply={(f) => setQ(typeof f.q === "string" ? f.q : "")}
      />

      {selected.size > 0 && (
        <BulkTagBar
          entityType="customer"
          selectedIds={Array.from(selected)}
          onApplied={() => loadTags(Array.from(selected))}
          onClear={() => setSelected(new Set())}
        />
      )}

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <Card className="overflow-hidden">
        {loading ? (
          <div className="space-y-0 divide-y">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-4 py-3">
                <Skeleton className="h-4 w-4 shrink-0 rounded" />
                <Skeleton className="h-4 w-36" />
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-4 w-16" />
                <Skeleton className="ml-auto h-4 w-24" />
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="p-10 text-center text-sm text-muted-foreground">{t("empty")}</div>
        ) : (
          <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-sm">
            <thead className="bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="w-10 px-4 py-3 text-left font-medium">
                  <input
                    type="checkbox"
                    aria-label={tCommon("selectAll")}
                    className="h-4 w-4 rounded border-input"
                    checked={items.length > 0 && selected.size === items.length}
                    onChange={toggleAll}
                  />
                </th>
                <th className="px-4 py-3 text-left font-medium">{t("name")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("company")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("country")}</th>
                <th className="px-4 py-3 text-left font-medium">{tTags("title")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("created")}</th>
                <th className="px-4 py-3 text-right font-medium">{tCommon("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} className="border-t hover:bg-muted/30">
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      aria-label={tCommon("select")}
                      className="h-4 w-4 rounded border-input"
                      checked={selected.has(c.id)}
                      onChange={() => toggleRow(c.id)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/${locale}/customers/${c.id}`}
                      className="font-medium text-primary hover:underline"
                    >
                      {c.first_name} {c.last_name}
                    </Link>
                    {c.email && <div className="text-xs text-muted-foreground">{c.email}</div>}
                  </td>
                  <td className="px-4 py-3">{c.company ?? "—"}</td>
                  <td className="px-4 py-3">{c.country ?? "—"}</td>
                  <td className="px-4 py-3">
                    <TagChipList tags={tagMap[c.id] ?? []} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(c.created_at).toLocaleDateString(locale)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <Button asChild variant="ghost" size="icon" aria-label={tCommon("edit")}>
                        <Link href={`/${locale}/customers/${c.id}/edit`}>
                          <Pencil className="h-4 w-4" />
                        </Link>
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={tCommon("delete")}
                        onClick={() => handleDelete(c)}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </Card>

      {hasMore && (
        <div className="flex justify-center">
          <Button type="button" variant="outline" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? tCommon("loading") : tCommon("loadMore")}
          </Button>
        </div>
      )}
    </div>
  );
}
