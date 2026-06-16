"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Package, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useConfirm } from "@/components/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
import { type Product } from "@/lib/api";
import { useDeleteProduct, useProductsInfinite } from "@/lib/use-products";

export default function ProductsPage() {
  const t = useTranslations("products");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const confirm = useConfirm();

  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");

  useEffect(() => {
    const handle = setTimeout(() => setDebouncedQ(q), 200);
    return () => clearTimeout(handle);
  }, [q]);

  const productsQuery = useProductsInfinite(debouncedQ);
  const items = useMemo(
    () => productsQuery.data?.pages.flatMap((p) => p.items) ?? [],
    [productsQuery.data],
  );

  const deleteProduct = useDeleteProduct();
  const error =
    (productsQuery.isError && (productsQuery.error as Error).message) ||
    (deleteProduct.isError && (deleteProduct.error as Error).message) ||
    null;

  async function handleDelete(product: Product) {
    const ok = await confirm({
      title: tCommon("confirmDelete"),
      tone: "danger",
      confirmLabel: tCommon("delete"),
    });
    if (!ok) return;
    try {
      await deleteProduct.mutateAsync(product.id);
    } catch {
      /* surfaced via deleteProduct.isError */
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

  const loading = productsQuery.isLoading;

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
        {loading ? (
          <div className="space-y-0 divide-y">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-4 py-3">
                <Skeleton className="h-4 w-36" />
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-5 w-16 rounded-full" />
                <Skeleton className="ml-auto h-4 w-24" />
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
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

      {productsQuery.hasNextPage && (
        <div className="flex justify-center">
          <Button
            type="button"
            variant="outline"
            onClick={() => productsQuery.fetchNextPage()}
            disabled={productsQuery.isFetchingNextPage}
          >
            {productsQuery.isFetchingNextPage ? tCommon("loading") : tCommon("loadMore")}
          </Button>
        </div>
      )}
    </div>
  );
}
