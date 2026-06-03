"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Check, FileText, Loader2, Plus, ShieldAlert, Star, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type DocumentTemplate, type MergeField } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

/**
 * Admin/manager merge-field template editor on /settings.
 *
 * Operator-authored document bodies with `{{ token }}` placeholders. The
 * field picker lists the allow-listed catalog; clicking a field inserts
 * its token at the cursor. Applying a template to a contract happens on
 * the contract detail page, not here — this card only authors them.
 */
interface Props {
  canManage: boolean;
}

interface Draft {
  id: string | null;
  name: string;
  body: string;
  is_default: boolean;
}

const EMPTY: Draft = { id: null, name: "", body: "", is_default: false };

export function DocumentTemplatesCard({ canManage }: Props) {
  const t = useTranslations("documentTemplates");
  const [templates, setTemplates] = useState<DocumentTemplate[] | null>(null);
  const [fields, setFields] = useState<MergeField[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLTextAreaElement | null>(null);

  async function refresh() {
    const token = getToken();
    if (!token) return;
    try {
      setTemplates(await api.listDocumentTemplates(token));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    }
  }

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    refresh();
    api.listMergeFields(token).then(setFields).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startCreate() {
    setError(null);
    setDraft({ ...EMPTY });
  }

  function startEdit(tpl: DocumentTemplate) {
    setError(null);
    setDraft({ id: tpl.id, name: tpl.name, body: tpl.body, is_default: tpl.is_default });
  }

  function insertToken(token: string) {
    const snippet = `{{ ${token} }}`;
    const el = bodyRef.current;
    setDraft((d) => {
      if (!d) return d;
      if (!el) return { ...d, body: `${d.body}${snippet}` };
      const start = el.selectionStart ?? d.body.length;
      const end = el.selectionEnd ?? d.body.length;
      const next = d.body.slice(0, start) + snippet + d.body.slice(end);
      // Restore the caret after React re-renders.
      requestAnimationFrame(() => {
        el.focus();
        const pos = start + snippet.length;
        el.setSelectionRange(pos, pos);
      });
      return { ...d, body: next };
    });
  }

  async function save() {
    if (!draft || !draft.name.trim()) return;
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      if (draft.id) {
        await api.updateDocumentTemplate(token, draft.id, {
          name: draft.name.trim(),
          body: draft.body,
          is_default: draft.is_default,
        });
      } else {
        await api.createDocumentTemplate(token, {
          name: draft.name.trim(),
          body: draft.body,
          is_default: draft.is_default,
        });
      }
      setDraft(null);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove(tpl: DocumentTemplate) {
    if (!confirm(t("confirmDelete", { name: tpl.name }))) return;
    const token = getToken();
    if (!token) return;
    setError(null);
    try {
      await api.deleteDocumentTemplate(token, tpl.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            {t("title")}
          </CardTitle>
          {canManage && !draft && (
            <Button size="sm" onClick={startCreate}>
              <Plus className="h-4 w-4" />
              {t("new")}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {!canManage && (
          <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-900 dark:text-amber-200">
            <ShieldAlert className="h-4 w-4" />
            {t("adminOnly")}
          </div>
        )}

        <p className="text-xs text-muted-foreground">{t("intro")}</p>

        {error && <p className="text-sm text-destructive">{error}</p>}

        {draft && (
          <div className="space-y-3 rounded-md border p-3">
            <div className="space-y-1.5">
              <Label htmlFor="tpl-name">{t("nameLabel")}</Label>
              <Input
                id="tpl-name"
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                placeholder={t("namePlaceholder")}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tpl-body">{t("bodyLabel")}</Label>
              <textarea
                id="tpl-body"
                ref={bodyRef}
                className="flex min-h-48 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm"
                value={draft.body}
                onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                placeholder={t("bodyPlaceholder")}
              />
            </div>
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">{t("fieldsLabel")}</p>
              <div className="flex flex-wrap gap-1.5">
                {fields.map((f) => (
                  <button
                    key={f.token}
                    type="button"
                    onClick={() => insertToken(f.token)}
                    title={`${f.description} (e.g. ${f.example})`}
                    className="rounded-full border bg-background px-2 py-0.5 text-xs hover:border-foreground/40 hover:bg-muted"
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.is_default}
                onChange={(e) => setDraft({ ...draft, is_default: e.target.checked })}
              />
              {t("setDefault")}
            </label>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setDraft(null)}>
                {t("cancel")}
              </Button>
              <Button size="sm" onClick={save} disabled={busy || !draft.name.trim()}>
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                {t("save")}
              </Button>
            </div>
          </div>
        )}

        {templates === null ? (
          <div className="grid place-items-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : templates.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ul className="space-y-2">
            {templates.map((tpl) => (
              <li key={tpl.id} className="flex items-center justify-between gap-3 rounded-md border p-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 font-medium">
                    <span className="truncate">{tpl.name}</span>
                    {tpl.is_default && (
                      <span className="flex shrink-0 items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                        <Star className="h-3 w-3" />
                        {t("default")}
                      </span>
                    )}
                  </div>
                  <p className="truncate text-xs text-muted-foreground">
                    {tpl.body.slice(0, 80) || t("emptyBody")}
                  </p>
                </div>
                {canManage && (
                  <div className="flex shrink-0 items-center gap-1">
                    <Button size="sm" variant="outline" onClick={() => startEdit(tpl)}>
                      {t("edit")}
                    </Button>
                    <button
                      type="button"
                      onClick={() => remove(tpl)}
                      aria-label={t("delete")}
                      className={cn(
                        "rounded-md border border-transparent p-1.5 text-muted-foreground transition-colors",
                        "hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive",
                      )}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
