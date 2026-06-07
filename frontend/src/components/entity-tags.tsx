"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Check, Plus, X } from "lucide-react";
import { api, type Tag, type TaggableEntity } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

/**
 * Tag chips + inline picker for a single entity's detail page.
 *
 * Loads the org's tag catalogue plus this entity's current assignments, then
 * lets the user toggle tags on/off. Pure-additive: an entity with no tags just
 * shows the "add" affordance.
 */
interface Props {
  entityType: TaggableEntity;
  entityId: string;
}

function readable(hex: string): string {
  // Pick black/white text for contrast against the chip's background.
  const c = hex.replace("#", "");
  if (c.length !== 6) return "#fff";
  const r = parseInt(c.slice(0, 2), 16);
  const g = parseInt(c.slice(2, 4), 16);
  const b = parseInt(c.slice(4, 6), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.6 ? "#1e293b" : "#ffffff";
}

export function EntityTags({ entityType, entityId }: Props) {
  const t = useTranslations("tags");
  const [all, setAll] = useState<Tag[]>([]);
  const [assigned, setAssigned] = useState<Tag[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  async function load() {
    const token = getToken();
    if (!token) return;
    const [tags, assignments] = await Promise.all([
      api.listTags(token),
      api.listTagAssignments(token, entityType, [entityId]),
    ]);
    setAll(tags);
    setAssigned(assignments[0]?.tags ?? []);
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityType, entityId]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const assignedIds = new Set(assigned.map((tag) => tag.id));

  async function toggle(tag: Tag) {
    const token = getToken();
    if (!token || busy) return;
    setBusy(true);
    const isOn = assignedIds.has(tag.id);
    // Optimistic.
    setAssigned((prev) =>
      isOn ? prev.filter((x) => x.id !== tag.id) : [...prev, tag],
    );
    try {
      const body = { tag_id: tag.id, entity_type: entityType, entity_id: entityId };
      if (isOn) await api.unassignTag(token, body);
      else await api.assignTag(token, body);
    } catch {
      await load(); // reconcile on failure
    } finally {
      setBusy(false);
    }
  }

  return (
    <div ref={wrapRef} className="relative">
      <div className="flex flex-wrap items-center gap-1.5">
        {assigned.map((tag) => (
          <span
            key={tag.id}
            className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium"
            style={{ backgroundColor: tag.color, color: readable(tag.color) }}
          >
            {tag.name}
            <button
              type="button"
              onClick={() => toggle(tag)}
              aria-label={t("remove")}
              className="opacity-70 transition-opacity hover:opacity-100"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="inline-flex items-center gap-1 rounded-full border border-dashed px-2.5 py-0.5 text-xs text-muted-foreground transition-colors hover:border-solid hover:text-foreground"
        >
          <Plus className="h-3 w-3" />
          {t("addTag")}
        </button>
      </div>

      {open && (
        <div className="absolute z-20 mt-1.5 max-h-64 w-56 overflow-auto rounded-md border bg-popover p-1 shadow-md">
          {all.length === 0 ? (
            <p className="px-2 py-3 text-center text-xs text-muted-foreground">
              {t("noneYet")}
            </p>
          ) : (
            all.map((tag) => {
              const on = assignedIds.has(tag.id);
              return (
                <button
                  key={tag.id}
                  type="button"
                  onClick={() => toggle(tag)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent",
                    on && "font-medium",
                  )}
                >
                  <span
                    className="h-3 w-3 shrink-0 rounded-full"
                    style={{ backgroundColor: tag.color }}
                  />
                  <span className="min-w-0 flex-1 truncate">{tag.name}</span>
                  {on && <Check className="h-3.5 w-3.5 shrink-0 text-primary" />}
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
