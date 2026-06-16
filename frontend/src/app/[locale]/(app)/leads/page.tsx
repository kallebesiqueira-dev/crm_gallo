"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useQueryClient } from "@tanstack/react-query";
import { Download, Pencil, Plus, Search, Target, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { useConfirm } from "@/components/confirm-dialog";
import { TagChipList } from "@/components/entity-tags";
import { BulkTagBar } from "@/components/bulk-tag-bar";
import { SegmentBar } from "@/components/segment-bar";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
import { api, type Lead, type LeadStage } from "@/lib/api";
import { leadsKeys, useDeleteLead, useLeadsInfinite, useLeadTags } from "@/lib/use-leads";

const STAGE_VARIANT: Record<LeadStage, "default" | "secondary" | "success" | "warning" | "danger"> = {
  new: "secondary",
  contacted: "secondary",
  qualified: "default",
  proposal_sent: "warning",
  negotiation: "warning",
  won: "success",
  lost: "danger",
};

export default function LeadsPage() {
  const t = useTranslations("leads");
  const tStages = useTranslations("leads.stages");
  const tCommon = useTranslations("common");
  const tTags = useTranslations("tags");
  const locale = useLocale();
  const confirm = useConfirm();
  const qc = useQueryClient();

  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Debounce the search box into the query key (200ms) — same feel as the old
  // hand-rolled fetch timer, but now it just swaps the cached query.
  useEffect(() => {
    const handle = setTimeout(() => setDebouncedQ(q), 200);
    return () => clearTimeout(handle);
  }, [q]);

  const leadsQuery = useLeadsInfinite(debouncedQ);
  const leads = useMemo(
    () => leadsQuery.data?.pages.flatMap((p) => p.items) ?? [],
    [leadsQuery.data],
  );
  const ids = useMemo(() => leads.map((l) => l.id), [leads]);
  const tagsQuery = useLeadTags(ids);
  const tagMap = tagsQuery.data ?? {};

  const deleteLead = useDeleteLead();
  const error =
    (leadsQuery.isError && (leadsQuery.error as Error).message) ||
    (deleteLead.isError && (deleteLead.error as Error).message) ||
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
      prev.size === leads.length ? new Set() : new Set(leads.map((l) => l.id)),
    );
  }

  async function handleDelete(lead: Lead) {
    const ok = await confirm({
      title: tCommon("confirmDelete"),
      tone: "danger",
      confirmLabel: tCommon("delete"),
    });
    if (!ok) return;
    try {
      await deleteLead.mutateAsync(lead.id);
    } catch {
      /* surfaced via deleteLead.isError */
    }
  }

  const loading = leadsQuery.isLoading;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline">
            <a href={api.exportUrl("lead")}>
              <Download className="h-4 w-4" />
              {tCommon("exportCsv")}
            </a>
          </Button>
          <Button asChild>
            <Link href={`/${locale}/leads/new`}>
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
        entityType="lead"
        currentFilters={{ q }}
        onApply={(f) => setQ(typeof f.q === "string" ? f.q : "")}
      />

      {selected.size > 0 && (
        <BulkTagBar
          entityType="lead"
          selectedIds={Array.from(selected)}
          onApplied={() => qc.invalidateQueries({ queryKey: leadsKeys.all })}
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
                <Skeleton className="h-5 w-20 rounded-full" />
                <Skeleton className="h-4 w-16" />
                <Skeleton className="ml-auto h-4 w-24" />
              </div>
            ))}
          </div>
        ) : leads.length === 0 ? (
          <EmptyState
            icon={Target}
            title={t("empty")}
            actionLabel={t("new")}
            actionHref={`/${locale}/leads/new`}
          />
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
                    checked={leads.length > 0 && selected.size === leads.length}
                    onChange={toggleAll}
                  />
                </th>
                <th className="px-4 py-3 text-left font-medium">{t("name")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("company")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("stage")}</th>
                <th className="px-4 py-3 text-left font-medium">{tTags("title")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("score")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("created")}</th>
                <th className="px-4 py-3 text-right font-medium">{tCommon("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <tr key={lead.id} className="border-t hover:bg-muted/30">
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      aria-label={tCommon("select")}
                      className="h-4 w-4 rounded border-input"
                      checked={selected.has(lead.id)}
                      onChange={() => toggleRow(lead.id)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/${locale}/leads/${lead.id}`}
                      className="font-medium text-primary hover:underline"
                    >
                      {lead.first_name} {lead.last_name}
                    </Link>
                    {lead.email && (
                      <div className="text-xs text-muted-foreground">{lead.email}</div>
                    )}
                  </td>
                  <td className="px-4 py-3">{lead.company ?? "—"}</td>
                  <td className="px-4 py-3">
                    <Badge variant={STAGE_VARIANT[lead.stage]}>{tStages(lead.stage)}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    <TagChipList tags={tagMap[lead.id] ?? []} />
                  </td>
                  <td className="px-4 py-3">
                    {lead.ai_score != null ? (
                      <span className="font-mono">{lead.ai_score}</span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(lead.created_at).toLocaleDateString(locale)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <Button asChild variant="ghost" size="icon" aria-label={tCommon("edit")}>
                        <Link href={`/${locale}/leads/${lead.id}/edit`}>
                          <Pencil className="h-4 w-4" />
                        </Link>
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={tCommon("delete")}
                        onClick={() => handleDelete(lead)}
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

      {leadsQuery.hasNextPage && (
        <div className="flex justify-center">
          <Button
            type="button"
            variant="outline"
            onClick={() => leadsQuery.fetchNextPage()}
            disabled={leadsQuery.isFetchingNextPage}
          >
            {leadsQuery.isFetchingNextPage ? tCommon("loading") : tCommon("loadMore")}
          </Button>
        </div>
      )}
    </div>
  );
}
