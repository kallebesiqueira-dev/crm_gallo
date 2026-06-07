"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Plus, ShieldAlert, SlidersHorizontal, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  api,
  type CustomFieldDefinition,
  type CustomFieldEntity,
  type CustomFieldKind,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

/**
 * Admin/manager custom-field editor on /settings.
 *
 * Lets privileged users declare the org's per-entity custom-field schema
 * (the `custom_field_definitions` rows). Pick an entity type, see its live
 * definitions, add a new one, or soft-delete an existing one. The values
 * themselves are entered on each entity's form via CustomFieldsInput.
 *
 * `entity_type` + `key` are immutable server-side, so editing is limited to
 * delete + re-create here — keeps the UI honest about the backend contract.
 */
interface Props {
  canManage: boolean;
}

const ENTITIES: CustomFieldEntity[] = ["lead", "customer", "deal", "company"];

const KINDS: CustomFieldKind[] = [
  "text",
  "textarea",
  "number",
  "date",
  "boolean",
  "select",
  "multiselect",
  "url",
  "email",
];

const NEEDS_OPTIONS = (k: CustomFieldKind) => k === "select" || k === "multiselect";

export function CustomFieldsCard({ canManage }: Props) {
  const t = useTranslations("customFields");
  const [entity, setEntity] = useState<CustomFieldEntity>("lead");
  const [defs, setDefs] = useState<CustomFieldDefinition[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Create form
  const [key, setKey] = useState("");
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<CustomFieldKind>("text");
  const [required, setRequired] = useState(false);
  const [optionsText, setOptionsText] = useState("");
  const [creating, setCreating] = useState(false);

  async function refresh() {
    const token = getToken();
    if (!token) return;
    try {
      setDefs(await api.listCustomFields(token, entity));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    }
  }

  useEffect(() => {
    setDefs(null);
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entity]);

  function resetForm() {
    setKey("");
    setLabel("");
    setKind("text");
    setRequired(false);
    setOptionsText("");
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    if (!token || !key.trim() || !label.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const options = NEEDS_OPTIONS(kind)
        ? optionsText
            .split(",")
            .map((o) => o.trim())
            .filter(Boolean)
        : null;
      await api.createCustomField(token, {
        entity_type: entity,
        key: key.trim(),
        label: label.trim(),
        field_type: kind,
        required,
        options,
        position: defs?.length ?? 0,
      });
      resetForm();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  async function remove(d: CustomFieldDefinition) {
    const token = getToken();
    if (!token) return;
    if (!confirm(t("confirmDelete", { label: d.label }))) return;
    setError(null);
    try {
      await api.deleteCustomField(token, d.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4" />
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

        <p className="text-xs text-muted-foreground">{t("intro")}</p>

        <div className="flex flex-wrap gap-1.5">
          {ENTITIES.map((e) => (
            <Button
              key={e}
              type="button"
              size="sm"
              variant={e === entity ? "default" : "outline"}
              onClick={() => setEntity(e)}
            >
              {t(`entity.${e}`)}
            </Button>
          ))}
        </div>

        {canManage && (
          <form onSubmit={create} className="grid gap-3 rounded-md border p-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="cf_key">{t("key")}</Label>
              <Input
                id="cf_key"
                value={key}
                onChange={(e) => setKey(e.target.value.toLowerCase())}
                placeholder={t("keyPlaceholder")}
                pattern="[a-z][a-z0-9_]*"
                required
              />
              <p className="text-[11px] text-muted-foreground">{t("keyHint")}</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cf_label">{t("label")}</Label>
              <Input
                id="cf_label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder={t("labelPlaceholder")}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cf_kind">{t("type")}</Label>
              <select
                id="cf_kind"
                aria-label={t("type")}
                value={kind}
                onChange={(e) => setKind(e.target.value as CustomFieldKind)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {t(`kind.${k}`)}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-end gap-2 pb-1.5">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-input"
                  checked={required}
                  onChange={(e) => setRequired(e.target.checked)}
                />
                {t("required")}
              </label>
            </div>
            {NEEDS_OPTIONS(kind) && (
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="cf_options">{t("options")}</Label>
                <Input
                  id="cf_options"
                  value={optionsText}
                  onChange={(e) => setOptionsText(e.target.value)}
                  placeholder={t("optionsPlaceholder")}
                />
                <p className="text-[11px] text-muted-foreground">{t("optionsHint")}</p>
              </div>
            )}
            <div className="sm:col-span-2">
              <Button
                type="submit"
                disabled={creating || !key.trim() || !label.trim()}
              >
                {creating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4" />
                )}
                {t("add")}
              </Button>
            </div>
          </form>
        )}

        {defs === null ? (
          <div className="grid place-items-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : defs.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ul className="space-y-2">
            {defs.map((d) => (
              <li
                key={d.id}
                className="flex items-center justify-between gap-3 rounded-md border p-3"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2 font-medium">
                    {d.label}
                    {d.required && (
                      <span className="rounded-full bg-destructive/15 px-2 py-0.5 text-[11px] font-medium text-destructive">
                        {t("required")}
                      </span>
                    )}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    <code className="font-mono">{d.key}</code> · {t(`kind.${d.field_type}`)}
                    {d.options && d.options.length > 0 && ` · ${d.options.join(", ")}`}
                  </div>
                </div>
                {canManage && (
                  <button
                    type="button"
                    onClick={() => remove(d)}
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
      </CardContent>
    </Card>
  );
}
