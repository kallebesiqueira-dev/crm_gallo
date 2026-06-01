"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, MessageSquarePlus, Pencil, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type Note } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Per-entity notes panel. Mounted on lead / customer / deal detail
 * pages alongside the ActivityTimeline.
 *
 * Markdown rendering is intentionally NOT bundled in v1 — the body
 * is shown as `whitespace-pre-wrap` plain text so URLs, line breaks
 * and indentation render but headings / lists do not. A future PR
 * can swap in `react-markdown` without an API change.
 *
 * Permissions:
 *   - List + create: any org member who can read the entity.
 *   - Edit + delete: enforced by the backend (`ensure_can_mutate`
 *     against the note's author OR admin/manager). Frontend doesn't
 *     hide the buttons — clicking when you're not allowed surfaces
 *     a friendly 403 inline.
 */
interface Props {
  entityType: "lead" | "customer" | "deal";
  entityId: string;
}

export function NotesPanel({ entityType, entityId }: Props) {
  const t = useTranslations("notes");
  const [items, setItems] = useState<Note[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Compose form
  const [newBody, setNewBody] = useState("");
  const [posting, setPosting] = useState(false);

  // Inline edit
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editBody, setEditBody] = useState("");
  const [savingId, setSavingId] = useState<string | null>(null);

  async function refresh() {
    try {
      setItems(await api.listNotes(entityType, entityId));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityType, entityId]);

  async function submitNew(e: React.FormEvent) {
    e.preventDefault();
    const body = newBody.trim();
    if (!body) return;
    setPosting(true);
    setError(null);
    try {
      await api.createNote(entityType, entityId, body);
      setNewBody("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add note");
    } finally {
      setPosting(false);
    }
  }

  function startEdit(n: Note) {
    setEditingId(n.id);
    setEditBody(n.body);
  }

  function cancelEdit() {
    setEditingId(null);
    setEditBody("");
  }

  async function saveEdit(n: Note) {
    const body = editBody.trim();
    if (!body || body === n.body) {
      cancelEdit();
      return;
    }
    setSavingId(n.id);
    setError(null);
    try {
      await api.updateNote(n.id, body);
      cancelEdit();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSavingId(null);
    }
  }

  async function remove(n: Note) {
    if (!confirm(t("confirmDelete"))) return;
    setError(null);
    try {
      await api.deleteNote(n.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageSquarePlus className="h-4 w-4" />
          {t("title")}
          {items && (
            <span className="text-xs font-normal text-muted-foreground">
              ({items.length})
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        <form onSubmit={submitNew} className="space-y-2">
          <textarea
            value={newBody}
            onChange={(e) => setNewBody(e.target.value)}
            placeholder={t("placeholder")}
            rows={3}
            className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <div className="flex justify-end">
            <Button type="submit" size="sm" disabled={posting || !newBody.trim()}>
              {posting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : t("post")}
            </Button>
          </div>
        </form>

        {items === null ? (
          <div className="grid place-items-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ul className="space-y-3">
            {items.map((n) => {
              const isEditing = editingId === n.id;
              return (
                <li
                  key={n.id}
                  className="rounded-md border bg-muted/30 p-3 text-sm"
                >
                  <div className="mb-1 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                    <span>
                      <strong className="font-medium text-foreground">
                        {n.author_name || n.author_email || t("unknownAuthor")}
                      </strong>
                      {" · "}
                      {formatWhen(n.created_at)}
                      {n.updated_at !== n.created_at && (
                        <span className="ml-1 italic">({t("edited")})</span>
                      )}
                    </span>
                    {!isEditing && (
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => startEdit(n)}
                          aria-label={t("edit")}
                          className="rounded p-1 text-muted-foreground hover:bg-background hover:text-foreground"
                        >
                          <Pencil className="h-3 w-3" />
                        </button>
                        <button
                          type="button"
                          onClick={() => remove(n)}
                          aria-label={t("delete")}
                          className={cn(
                            "rounded p-1 text-muted-foreground transition-colors",
                            "hover:bg-destructive/10 hover:text-destructive",
                          )}
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    )}
                  </div>
                  {isEditing ? (
                    <div className="space-y-2">
                      <textarea
                        value={editBody}
                        onChange={(e) => setEditBody(e.target.value)}
                        rows={Math.max(3, editBody.split("\n").length)}
                        className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                      />
                      <div className="flex justify-end gap-2">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={cancelEdit}
                        >
                          <X className="h-3 w-3" />
                          {t("cancel")}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => saveEdit(n)}
                          disabled={savingId === n.id}
                        >
                          {savingId === n.id ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            t("save")
                          )}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    // `whitespace-pre-wrap` preserves the user's
                    // line breaks + indentation. Full markdown
                    // rendering is a follow-up (`react-markdown`).
                    <div className="whitespace-pre-wrap break-words text-sm">
                      {n.body}
                    </div>
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

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
