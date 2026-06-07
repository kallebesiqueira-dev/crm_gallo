"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Bookmark, BookmarkPlus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, type SavedSegment, type TaggableEntity } from "@/lib/api";
import { getToken } from "@/lib/auth";

/**
 * Saved-segment (stored list filter) bar for a list page.
 *
 * Lists the org's saved segments for this entity type as one-click chips that
 * push their stored filter blob back to the parent. "Save current" snapshots
 * the page's live filters under a name. Filters are opaque JSON — the parent
 * owns both producing `currentFilters` and interpreting them on apply.
 */
interface Props {
  entityType: TaggableEntity;
  currentFilters: Record<string, unknown>;
  onApply: (filters: Record<string, unknown>) => void;
}

export function SegmentBar({ entityType, currentFilters, onApply }: Props) {
  const t = useTranslations("segments");
  const [segments, setSegments] = useState<SavedSegment[]>([]);

  async function refresh() {
    const token = getToken();
    if (!token) return;
    try {
      setSegments(await api.listSegments(token, entityType));
    } catch {
      setSegments([]);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityType]);

  async function save() {
    const token = getToken();
    if (!token) return;
    const name = window.prompt(t("savePrompt"));
    if (!name || !name.trim()) return;
    try {
      await api.createSegment(token, {
        entity_type: entityType,
        name: name.trim(),
        filters: currentFilters,
      });
      await refresh();
    } catch {
      /* ignore — non-critical */
    }
  }

  async function remove(seg: SavedSegment) {
    const token = getToken();
    if (!token) return;
    if (!window.confirm(t("confirmDelete", { name: seg.name }))) return;
    try {
      await api.deleteSegment(token, seg.id);
      await refresh();
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <Bookmark className="h-3.5 w-3.5" />
        {t("title")}
      </span>
      {segments.length === 0 ? (
        <span className="text-xs text-muted-foreground">{t("empty")}</span>
      ) : (
        segments.map((seg) => (
          <span
            key={seg.id}
            className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs"
          >
            <button
              type="button"
              onClick={() => onApply(seg.filters)}
              className="font-medium hover:underline"
            >
              {seg.name}
            </button>
            <button
              type="button"
              onClick={() => remove(seg)}
              aria-label={t("delete")}
              className="text-muted-foreground hover:text-destructive"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))
      )}
      <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={save}>
        <BookmarkPlus className="h-3.5 w-3.5" />
        {t("save")}
      </Button>
    </div>
  );
}
