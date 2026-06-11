"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Package, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useConfirm } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { api, type Product } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function ProductsPage() {
  const t = useTranslations("products");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const confirm = useConfirm();
  const [items, setItems] = useState<Product[]>([]);
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    const handle = setTimeout(() => {
      api
        .listProducts(token, { q: q || undefined })
        .then((page) => {
          setItems(page.items);
          setCursor(page.next_cursor);
          setHasMore(page.has_more);
        })
        .catch(() => {
          setItems([]);
          setCursor(null);
          setHasMore(false);
        });
    }, 200);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  async function loadMore() {
    const token = getToken();
    if (!token || !cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await api.listProducts(token, { q: q || undefined, cursor });
      setItems((prev) => [...prev, ...page.items]);
      setCursor(page.next_cursor);
      setHasMore(page.has_more);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleDelete(product: Product) {
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
      await api.deleteProduct(token, product.id);
      setItems((prev) => prev.filter((p) => p.id !== product.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  function fmtPrice(p: Product) {
    if (p.price == null || p.price === "") return "—";
    const n = Number(p.price);
    if (Number.isNaN(n)) return p.price;
    try {
      return new Intl.NumberFormat(locale, { style: "currency", currency: p.currency || "EUR" }).format(n);
    } catch {
      return `${p.currency} ${n.toFixed(2)}`;
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <Button asChild>
          <Link href={`/${locale}/products/new`}>
            <Plus className="h-4 w-4" />
            {t("new")}
          </Link>
        </Button>
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

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <Card className="overflow-hidden">
        {items.length === 0 ? (
          <EmptyState
            icon={Package}
            title={t("empty")}
            actionLabel={t("new")}
            actionHref={`/${locale}/products/new`}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-sm">
              <thead className="bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">{t("name")}</th>
                  <th className="px-4 py-3 text-left font-medium">{t("sku")}</th>
                  <th className="px-4 py-3 text-left font-medium">{t("type")}</th>
                  <th className="px-4 py-3 text-right font-medium">{t("price")}</th>
                  <th className="px-4 py-3 text-left font-medium">{t("status")}</th>
                  <th className="px-4 py-3 text-right font-medium">{tCommon("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((p) => (
                  <tr key={p.id} className="border-t hover:bg-muted/30">
                    <td className="px-4 py-3">
                      <Link
                        href={`/${locale}/products/${p.id}/edit`}
                        className="font-medium text-primary hover:underline"
                      >
                        {p.name}
                      </Link>
                      {p.unit && <div className="text-xs text-muted-foreground">/ {p.unit}</div>}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{p.sku ?? "—"}</td>
                    <td className="px-4 py-3">
                      {p.type === "service" ? t("typeService") : t("typeProduct")}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{fmtPrice(p)}</td>
                    <td className="px-4 py-3">
                      <span
                        className={
                          p.active
                            ? "inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400"
                            : "inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground"
                        }
                      >
                        {p.active ? t("active") : t("inactive")}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <Button asChild variant="ghost" size="icon" aria-label={tCommon("edit")}>
                          <Link href={`/${locale}/products/${p.id}/edit`}>
                            <Pencil className="h-4 w-4" />
                          </Link>
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          aria-label={tCommon("delete")}
                          onClick={() => handleDelete(p)}
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
