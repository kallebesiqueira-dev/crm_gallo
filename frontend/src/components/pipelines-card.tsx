"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Check,
  GitBranch,
  Loader2,
  Plus,
  ShieldAlert,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type Pipeline, type PipelineStageDraft } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Admin/manager pipeline editor on /settings.
 *
 * Phase 1 scope (matches backend):
 *   - View all pipelines (auto-seeded "Default lead funnel" + "Default
 *     sales funnel" on first read).
 *   - Create a new (empty) pipeline of kind lead|deal.
 *   - Inline-edit stages: rename, change probability, mark won/lost,
 *     add/remove rows. Save commits the whole stage list via the
 *     reconcile PATCH endpoint.
 *   - Promote a non-default to default (demotes the previous one
 *     server-side).
 *   - Delete a non-default pipeline. Default refuses with 400 (the
 *     backend would just re-seed it).
 *
 * Phase 2 (next round) wires Lead/Deal to pipeline_stage_id and
 * the kanban / list pages start respecting custom stage sets.
 */
interface Props {
  canManage: boolean;
}

const EMPTY_DRAFT: PipelineStageDraft = {
  id: null,
  name: "",
  position: 0,
  probability: 10,
  is_won: false,
  is_lost: false,
};

export function PipelinesCard({ canManage }: Props) {
  const t = useTranslations("pipelines");
  const [pipelines, setPipelines] = useState<Pipeline[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Create form
  const [newName, setNewName] = useState("");
  const [newKind, setNewKind] = useState<"lead" | "deal">("lead");
  const [creating, setCreating] = useState(false);

  // Inline-edit state per pipeline (drafts keyed by pipeline id).
  const [editing, setEditing] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<PipelineStageDraft[]>([]);
  const [saving, setSaving] = useState(false);

  async function refresh() {
    try {
      setPipelines(await api.listPipelines());
      setError(null);
    } catch (e) {
      // 403 for non-privileged — render the friendly notice but
      // surface as empty rather than scary error text.
      if (e instanceof Error && e.message.toLowerCase().includes("insufficient role")) {
        setPipelines([]);
      } else {
        setError(e instanceof Error ? e.message : "Load failed");
      }
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startEdit(p: Pipeline) {
    setEditing(p.id);
    // Clone the existing stages so cancel can throw the draft away.
    setDrafts(
      p.stages.map((s) => ({
        id: s.id,
        name: s.name,
        slug: s.slug,
        position: s.position,
        probability: s.probability,
        is_won: s.is_won,
        is_lost: s.is_lost,
      })),
    );
  }

  function cancelEdit() {
    setEditing(null);
    setDrafts([]);
  }

  function addRow() {
    setDrafts((d) => [
      ...d,
      { ...EMPTY_DRAFT, position: d.length },
    ]);
  }

  function removeRow(i: number) {
    setDrafts((d) => d.filter((_, j) => j !== i).map((row, idx) => ({ ...row, position: idx })));
  }

  function patchRow(i: number, patch: Partial<PipelineStageDraft>) {
    setDrafts((d) => d.map((row, j) => (j === i ? { ...row, ...patch } : row)));
  }

  async function saveStages(p: Pipeline) {
    setSaving(true);
    setError(null);
    try {
      await api.updatePipeline(p.id, { stages: drafts });
      cancelEdit();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function setDefault(p: Pipeline) {
    setError(null);
    try {
      await api.updatePipeline(p.id, { is_default: true });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    }
  }

  async function remove(p: Pipeline) {
    if (!confirm(t("confirmDelete", { name: p.name }))) return;
    setError(null);
    try {
      await api.deletePipeline(p.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api.createPipeline(newKind, newName.trim());
      setNewName("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <GitBranch className="h-4 w-4" />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {!canManage && (
          <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-900 dark:text-amber-200">
            <ShieldAlert className="h-4 w-4" />
            {t("adminOnly")}
          </div>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        <p className="text-xs text-muted-foreground">{t("phase1Notice")}</p>

        {canManage && (
          <form onSubmit={create} className="flex flex-wrap items-end gap-2">
            <div className="space-y-1.5">
              <Label htmlFor="new_pipeline_kind">{t("kindLabel")}</Label>
              <select
                id="new_pipeline_kind"
                aria-label={t("kindLabel")}
                value={newKind}
                onChange={(e) => setNewKind(e.target.value as "lead" | "deal")}
                className="flex h-10 rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="lead">{t("kindLead")}</option>
                <option value="deal">{t("kindDeal")}</option>
              </select>
            </div>
            <div className="min-w-[200px] flex-1 space-y-1.5">
              <Label htmlFor="new_pipeline_name">{t("nameLabel")}</Label>
              <Input
                id="new_pipeline_name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder={t("namePlaceholder")}
                required
              />
            </div>
            <Button type="submit" disabled={creating || !newName.trim()}>
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              {t("create")}
            </Button>
          </form>
        )}

        {pipelines === null ? (
          <div className="grid place-items-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : pipelines.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ul className="space-y-3">
            {pipelines.map((p) => {
              const isEditing = editing === p.id;
              return (
                <li key={p.id} className="rounded-md border p-3">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2 font-medium">
                        {p.name}
                        {p.is_default && (
                          <span className="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                            <Star className="h-3 w-3" />
                            {t("default")}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        <code className="font-mono">{p.kind}</code> · <code className="font-mono">{p.slug}</code>
                      </div>
                    </div>
                    {canManage && !isEditing && (
                      <div className="flex items-center gap-1">
                        {!p.is_default && (
                          <button
                            type="button"
                            onClick={() => setDefault(p)}
                            aria-label={t("setDefault")}
                            className="rounded-md border border-transparent p-1.5 text-muted-foreground hover:border-foreground/30 hover:bg-muted hover:text-foreground"
                          >
                            <Star className="h-3.5 w-3.5" />
                          </button>
                        )}
                        <Button size="sm" variant="outline" onClick={() => startEdit(p)}>
                          {t("editStages")}
                        </Button>
                        {!p.is_default && (
                          <button
                            type="button"
                            onClick={() => remove(p)}
                            aria-label={t("delete")}
                            className={cn(
                              "rounded-md border border-transparent p-1.5 text-muted-foreground transition-colors",
                              "hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive",
                            )}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    )}
                  </div>

                  {isEditing ? (
                    <div className="space-y-2">
                      <ol className="space-y-2">
                        {drafts.map((row, i) => (
                          <li
                            key={i}
                            className="grid grid-cols-12 items-center gap-2 rounded border bg-background p-2"
                          >
                            <span className="col-span-1 text-center text-xs text-muted-foreground">
                              #{i + 1}
                            </span>
                            <Input
                              className="col-span-5"
                              value={row.name}
                              placeholder={t("stageName")}
                              onChange={(e) => patchRow(i, { name: e.target.value })}
                            />
                            <div className="col-span-3 flex items-center gap-1">
                              <Input
                                type="number"
                                min={0}
                                max={100}
                                value={row.probability}
                                onChange={(e) =>
                                  patchRow(i, { probability: Number(e.target.value) })
                                }
                              />
                              <span className="text-xs text-muted-foreground">%</span>
                            </div>
                            <label className="col-span-1 flex items-center justify-center gap-1 text-xs">
                              <input
                                type="checkbox"
                                checked={row.is_won}
                                onChange={(e) =>
                                  patchRow(i, {
                                    is_won: e.target.checked,
                                    is_lost: e.target.checked ? false : row.is_lost,
                                  })
                                }
                              />
                              {t("won")}
                            </label>
                            <label className="col-span-1 flex items-center justify-center gap-1 text-xs">
                              <input
                                type="checkbox"
                                checked={row.is_lost}
                                onChange={(e) =>
                                  patchRow(i, {
                                    is_lost: e.target.checked,
                                    is_won: e.target.checked ? false : row.is_won,
                                  })
                                }
                              />
                              {t("lost")}
                            </label>
                            <button
                              type="button"
                              onClick={() => removeRow(i)}
                              aria-label={t("removeStage")}
                              className="col-span-1 grid place-items-center rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </li>
                        ))}
                      </ol>
                      <div className="flex justify-between">
                        <Button type="button" variant="outline" size="sm" onClick={addRow}>
                          <Plus className="h-3.5 w-3.5" />
                          {t("addStage")}
                        </Button>
                        <div className="flex gap-2">
                          <Button type="button" variant="ghost" size="sm" onClick={cancelEdit}>
                            {t("cancel")}
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            onClick={() => saveStages(p)}
                            disabled={saving || drafts.length === 0}
                          >
                            {saving ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Check className="h-3.5 w-3.5" />
                            )}
                            {t("save")}
                          </Button>
                        </div>
                      </div>
                    </div>
                  ) : p.stages.length === 0 ? (
                    <p className="text-xs text-muted-foreground">{t("noStages")}</p>
                  ) : (
                    <ol className="flex flex-wrap items-center gap-1.5">
                      {p.stages.map((s) => (
                        <li
                          key={s.id}
                          className={cn(
                            "flex items-center gap-1 rounded-full px-2 py-0.5 text-xs",
                            s.is_won && "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
                            s.is_lost && "bg-destructive/15 text-destructive",
                            !s.is_won && !s.is_lost && "bg-muted text-foreground",
                          )}
                        >
                          <span>{s.name}</span>
                          <span className="text-[10px] text-muted-foreground">
                            {s.probability}%
                          </span>
                        </li>
                      ))}
                    </ol>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
