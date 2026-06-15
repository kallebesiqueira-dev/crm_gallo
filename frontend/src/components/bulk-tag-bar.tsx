"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { api, type Tag, type TaggableEntity } from "@/lib/api";
import { getToken } from "@/lib/auth";

/**
 * Bulk tag/untag toolbar shown above a list once one or more rows are
 * selected. Adds or removes a single chosen tag across every selected entity
 * in one request via /api/tags/bulk, then asks the parent to refresh chips.
 */
interface Props {
  entityType: TaggableEntity;
  selectedIds: string[];
  onApplied: () => void;
  onClear: () => void;
}

export function BulkTagBar({ entityType, selectedIds, onApplied, onClear }: Props) {
  const t = useTranslations("tags");
  const [tags, setTags] = useState<Tag[]>([]);
  const [tagId, setTagId] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api
      .listTags(token)
      .then((rows) => {
        setTags(rows);
        if (rows.length > 0) setTagId((cur) => cur || rows[0].id);
      })
      .catch(() => setTags([]));
  }, []);

  async function apply(action: "add" | "remove") {
    const token = getToken();
    if (!token || !tagId || busy || selectedIds.length === 0) return;
    setBusy(true);
    try {
      await api.bulkTag(token, {
        tag_ids: [tagId],
        entity_type: entityType,
        entity_ids: selectedIds,
        action,
      });
      onApplied();
      onClear();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 px-3 py-2 text-sm">
      <span className="font-medium">{t("selected", { count: selectedIds.length })}</span>
      <Select
        aria-label={t("pickTag")}
        value={tagId}
        onChange={(e) => setTagId(e.target.value)}
      >
        {tags.length === 0 ? (
          <option value="">{t("noneYet")}</option>
        ) : (
          tags.map((tag) => (
            <option key={tag.id} value={tag.id}>
              {tag.name}
            </option>
          ))
        )}
      </Select>
      <Button type="button" size="sm" disabled={busy || !tagId} onClick={() => apply("add")}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
        {t("addToSelected")}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={busy || !tagId}
        onClick={() => apply("remove")}
      >
        <X className="h-4 w-4" />
        {t("removeFromSelected")}
      </Button>
      <button
        type="button"
        onClick={onClear}
        className="ml-auto text-xs text-muted-foreground hover:text-foreground"
      >
        {t("clearSelection")}
      </button>
    </div>
  );
}
