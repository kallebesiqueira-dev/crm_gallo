"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Plus, ShieldAlert, Tags as TagsIcon, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type Tag } from "@/lib/api";
import { getToken } from "@/lib/auth";

/**
 * Org-wide tag manager on /settings.
 *
 * Any member can create a tag (daily-driver action); only admin/manager can
 * rename, recolour, or delete (those change the tag for everyone). Renaming
 * is inline — click the name to edit. Deleting also strips the tag from every
 * entity it's attached to, server-side.
 */
interface Props {
  canManage: boolean;
}

const DEFAULT_COLOR = "#64748b";

export function TagsCard({ canManage }: Props) {
  const t = useTranslations("tags");
  const [tags, setTags] = useState<Tag[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [color, setColor] = useState(DEFAULT_COLOR);
  const [creating, setCreating] = useState(false);

  async function refresh() {
    const token = getToken();
    if (!token) return;
    try {
      setTags(await api.listTags(token));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    if (!token || !name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api.createTag(token, { name: name.trim(), color });
      setName("");
      setColor(DEFAULT_COLOR);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  async function recolor(tag: Tag, newColor: string) {
    const token = getToken();
    if (!token) return;
    setError(null);
    try {
      await api.updateTag(token, tag.id, { color: newColor });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    }
  }

  async function rename(tag: Tag, newName: string) {
    const trimmed = newName.trim();
    if (!trimmed || trimmed === tag.name) return;
    const token = getToken();
    if (!token) return;
    setError(null);
    try {
      await api.updateTag(token, tag.id, { name: trimmed });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    }
  }

  async function remove(tag: Tag) {
    const token = getToken();
    if (!token) return;
    if (!confirm(t("confirmDelete", { name: tag.name }))) return;
    setError(null);
    try {
      await api.deleteTag(token, tag.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TagsIcon className="h-4 w-4" />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {error && <p className="text-sm text-destructive">{error}</p>}

        <p className="text-xs text-muted-foreground">{t("intro")}</p>

        <form onSubmit={create} className="flex flex-wrap items-end gap-3 rounded-md border p-3">
          <div className="space-y-1.5">
            <Label htmlFor="tag_color">{t("color")}</Label>
            <input
              id="tag_color"
              type="color"
              aria-label={t("color")}
              value={color}
              onChange={(e) => setColor(e.target.value)}
              className="h-10 w-14 cursor-pointer rounded-md border border-input bg-background p-1"
            />
          </div>
          <div className="min-w-[12rem] flex-1 space-y-1.5">
            <Label htmlFor="tag_name">{t("name")}</Label>
            <Input
              id="tag_name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("namePlaceholder")}
              maxLength={60}
              required
            />
          </div>
          <Button type="submit" disabled={creating || !name.trim()}>
            {creating ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            {t("add")}
          </Button>
        </form>

        {tags === null ? (
          <div className="grid place-items-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : tags.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ul className="space-y-2">
            {tags.map((tag) => (
              <li
                key={tag.id}
                className="flex items-center justify-between gap-3 rounded-md border p-2.5"
              >
                <div className="flex min-w-0 items-center gap-2.5">
                  {canManage ? (
                    <input
                      type="color"
                      aria-label={t("color")}
                      value={tag.color}
                      onChange={(e) => recolor(tag, e.target.value)}
                      className="h-6 w-6 shrink-0 cursor-pointer rounded-full border-0 bg-transparent p-0"
                    />
                  ) : (
                    <span
                      className="h-4 w-4 shrink-0 rounded-full"
                      style={{ backgroundColor: tag.color }}
                    />
                  )}
                  {canManage ? (
                    <input
                      defaultValue={tag.name}
                      onBlur={(e) => rename(tag, e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") e.currentTarget.blur();
                      }}
                      aria-label={t("name")}
                      className="min-w-0 truncate rounded-md border border-transparent bg-transparent px-1.5 py-0.5 text-sm font-medium hover:border-input focus:border-input focus:outline-none"
                    />
                  ) : (
                    <span className="truncate text-sm font-medium">{tag.name}</span>
                  )}
                </div>
                {canManage && (
                  <button
                    type="button"
                    onClick={() => remove(tag)}
                    aria-label={t("delete")}
                    className="shrink-0 rounded-md border border-transparent p-1.5 text-muted-foreground transition-colors hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        {!canManage && (
          <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-900 dark:text-amber-200">
            <ShieldAlert className="h-4 w-4 shrink-0" />
            {t("memberNote")}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
