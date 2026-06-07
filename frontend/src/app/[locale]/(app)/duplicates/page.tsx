"use client";

import { useCallback, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { GitMerge, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useConfirm } from "@/components/confirm-dialog";
import {
  api,
  type DuplicateEntity,
  type DuplicateGroup,
  type DuplicateRecord,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

const ENTITY_TYPES: DuplicateEntity[] = ["lead", "customer", "company"];

const MATCH_VARIANT: Record<DuplicateGroup["match_type"], "default" | "secondary" | "outline"> = {
  email: "default",
  phone: "secondary",
  name: "outline",
};

export default function DuplicatesPage() {
  const t = useTranslations("duplicates");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const confirm = useConfirm();

  const [entityType, setEntityType] = useState<DuplicateEntity>("lead");
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [survivors, setSurvivors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [mergingKey, setMergingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const groupKey = (g: DuplicateGroup) => `${g.match_type}:${g.key}`;

  const load = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.listDuplicates(token, entityType);
      setGroups(res.groups);
      // Default survivor for each group = first (oldest) record.
      const defaults: Record<string, string> = {};
      for (const g of res.groups) defaults[`${g.match_type}:${g.key}`] = g.records[0]?.id;
      setSurvivors(defaults);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
      setGroups([]);
    } finally {
      setLoading(false);
    }
  }, [entityType]);

  useEffect(() => {
    setNotice(null);
    load();
  }, [load]);

  async function handleMerge(group: DuplicateGroup) {
    const token = getToken();
    if (!token) return;
    const survivorId = survivors[groupKey(group)];
    if (!survivorId) return;
    const loserIds = group.records.map((r) => r.id).filter((id) => id !== survivorId);
    if (loserIds.length === 0) return;

    const ok = await confirm({
      title: t("confirmTitle"),
      description: t("confirmBody", { count: loserIds.length }),
      confirmLabel: t("merge"),
    });
    if (!ok) return;

    setMergingKey(groupKey(group));
    setError(null);
    setNotice(null);
    try {
      const res = await api.mergeDuplicates(token, {
        entity_type: entityType,
        survivor_id: survivorId,
        loser_ids: loserIds,
      });
      setNotice(t("merged", { count: res.merged_count }));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setMergingKey(null);
    }
  }

  function recordLine(r: DuplicateRecord): string {
    const bits = [r.email, r.phone].filter(Boolean);
    return bits.length ? bits.join(" · ") : "—";
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      <div className="flex gap-1 rounded-lg border bg-muted/30 p-1">
        {ENTITY_TYPES.map((et) => (
          <button
            key={et}
            type="button"
            onClick={() => setEntityType(et)}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              entityType === et
                ? "bg-background shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t(`entity.${et}`)}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      {notice && (
        <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
          {notice}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center p-10 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : groups.length === 0 ? (
        <Card className="p-10 text-center text-sm text-muted-foreground">{t("empty")}</Card>
      ) : (
        <div className="space-y-3">
          {groups.map((group) => {
            const key = groupKey(group);
            const survivorId = survivors[key];
            const merging = mergingKey === key;
            return (
              <Card key={key} className="p-4">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge variant={MATCH_VARIANT[group.match_type]}>
                      {t(`match.${group.match_type}`)}
                    </Badge>
                    <span className="text-sm font-medium">{group.key}</span>
                    <span className="text-xs text-muted-foreground">
                      {t("recordCount", { count: group.records.length })}
                    </span>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => handleMerge(group)}
                    disabled={merging || !survivorId}
                  >
                    {merging ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <GitMerge className="h-4 w-4" />
                    )}
                    {t("merge")}
                  </Button>
                </div>

                <p className="mb-2 text-xs text-muted-foreground">{t("pickSurvivor")}</p>
                <ul className="divide-y rounded-md border">
                  {group.records.map((r) => (
                    <li key={r.id} className="flex items-center gap-3 px-3 py-2">
                      <input
                        type="radio"
                        name={key}
                        aria-label={t("keep")}
                        className="h-4 w-4"
                        checked={survivorId === r.id}
                        onChange={() => setSurvivors((p) => ({ ...p, [key]: r.id }))}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">{r.label}</div>
                        <div className="truncate text-xs text-muted-foreground">
                          {recordLine(r)}
                        </div>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {new Date(r.created_at).toLocaleDateString(locale)}
                      </div>
                      {survivorId === r.id ? (
                        <Badge variant="success">{t("survivor")}</Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">{tCommon("delete")}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
