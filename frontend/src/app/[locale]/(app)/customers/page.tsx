"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useQueryClient } from "@tanstack/react-query";
import { Download, Pencil, Plus, Search, Trash2, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useConfirm } from "@/components/confirm-dialog";
import { TagChipList } from "@/components/entity-tags";
import { BulkTagBar } from "@/components/bulk-tag-bar";
import { SegmentBar } from "@/components/segment-bar";
import { DataTable, type Column } from "@/components/ui/data-table";
import { EmptyState } from "@/components/empty-state";
import { api, type Customer } from "@/lib/api";
import {
  customersKeys,
  useCustomersInfinite,
  useCustomerTags,
  useDeleteCustomer,
} from "@/lib/use-customers";

export default function CustomersPage() {
  const t = useTranslations("customers");
  const tCommon = useTranslations("common");
  const tTags = useTranslations("tags");
  const locale = useLocale();
  const confirm = useConfirm();
  const qc = useQueryClient();

  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Debounce the search box into the query key (200ms).
  useEffect(() => {
    const handle = setTimeout(() => setDebouncedQ(q), 200);
    return () => clearTimeout(handle);
  }, [q]);

  const customersQuery = useCustomersInfinite(debouncedQ);
  const items = useMemo(
    () => customersQuery.data?.pages.flatMap((p) => p.items) ?? [],
    [customersQuery.data],
  );
  const ids = useMemo(() => items.map((c) => c.id), [items]);
  const tagsQuery = useCustomerTags(ids);
  const tagMap = tagsQuery.data ?? {};

  const deleteCustomer = useDeleteCustomer();
  const error =
    (customersQuery.isError && (customersQuery.error as Error).message) ||
    (deleteCustomer.isError && (deleteCustomer.error as Error).message) ||
    null;

  // A fresh search is a fresh selection set.
  useEffect(() => {
    setSelected(new Set());
  }, [debouncedQ]);

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
    try {
      await deleteCustomer.mutateAsync(customer.id);
    } catch {
      /* surfaced via deleteCustomer.isError */
    }
  }

  const loading = customersQuery.isLoading;

  const columns: Column<Customer>[] = [
    {
      id: "name",
      header: t("name"),
      sortValue: (c) => `${c.first_name} ${c.last_name}`.toLowerCase(),
      cell: (c) => (
        <>
          <Link
            href={`/${locale}/customers/${c.id}`}
            className="font-medium text-primary hover:underline"
          >
            {c.first_name} {c.last_name}
          </Link>
          {c.email && <div className="text-xs text-muted-foreground">{c.email}</div>}
        </>
      ),
    },
    {
      id: "company",
      header: t("company"),
      sortValue: (c) => c.company?.toLowerCase() ?? null,
      cell: (c) => c.company ?? "—",
    },
    {
      id: "country",
      header: t("country"),
      sortValue: (c) => c.country ?? null,
      cell: (c) => c.country ?? "—",
    },
    {
      id: "tags",
      header: tTags("title"),
      cell: (c) => <TagChipList tags={tagMap[c.id] ?? []} />,
    },
    {
      id: "created",
      header: t("created"),
      sortValue: (c) => c.created_at,
      cell: (c) => (
        <span className="text-muted-foreground">
          {new Date(c.created_at).toLocaleDateString(locale)}
        </span>
      ),
    },
    {
      id: "actions",
      header: tCommon("actions"),
      align: "right",
      cell: (c) => (
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
      ),
    },
  ];

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
          onApplied={() => qc.invalidateQueries({ queryKey: customersKeys.all })}
          onClear={() => setSelected(new Set())}
        />
      )}

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <Card className="overflow-hidden">
        <DataTable<Customer>
          columns={columns}
          rows={items}
          getRowId={(c) => c.id}
          loading={loading}
          empty={
            <EmptyState
              icon={Users}
              title={t("empty")}
              actionLabel={t("new")}
              actionHref={`/${locale}/customers/new`}
            />
          }
          selectedIds={selected}
          onToggleRow={toggleRow}
          onToggleAll={toggleAll}
          selectAllLabel={tCommon("selectAll")}
          selectRowLabel={tCommon("select")}
        />
      </Card>

      {customersQuery.hasNextPage && (
        <div className="flex justify-center">
          <Button
            type="button"
            variant="outline"
            onClick={() => customersQuery.fetchNextPage()}
            disabled={customersQuery.isFetchingNextPage}
          >
            {customersQuery.isFetchingNextPage ? tCommon("loading") : tCommon("loadMore")}
          </Button>
        </div>
      )}
    </div>
  );
}
