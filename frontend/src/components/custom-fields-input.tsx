"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  type CustomFieldDefinition,
  type CustomFieldEntity,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

/**
 * Renders the org's custom fields for one entity type as form inputs.
 *
 * Self-contained: fetches the live definitions for `entityType` and owns
 * the widget-per-type mapping. The parent holds the `custom_fields`
 * object and receives the full updated map via `onChange`. An empty /
 * unset value drops the key so the backend treats it as "clear".
 *
 * Renders nothing when the org has no definitions for this entity — so
 * dropping it into a form is a no-op until an admin defines fields.
 */
interface Props {
  entityType: CustomFieldEntity;
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}

export function CustomFieldsInput({ entityType, value, onChange }: Props) {
  const t = useTranslations("customFields");
  const [defs, setDefs] = useState<CustomFieldDefinition[] | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api
      .listCustomFields(token, entityType)
      .then(setDefs)
      .catch(() => setDefs([]));
  }, [entityType]);

  if (!defs || defs.length === 0) return null;

  function set(key: string, v: unknown) {
    const next = { ...value };
    if (v === "" || v === null || (Array.isArray(v) && v.length === 0)) {
      delete next[key];
    } else {
      next[key] = v;
    }
    onChange(next);
  }

  return (
    <div className="space-y-3 sm:col-span-2">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">
        {t("sectionTitle")}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {defs.map((d) => (
          <FieldWidget
            key={d.id}
            def={d}
            value={value?.[d.key]}
            onChange={(v) => set(d.key, v)}
          />
        ))}
      </div>
    </div>
  );
}

function FieldWidget({
  def,
  value,
  onChange,
}: {
  def: CustomFieldDefinition;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const id = `cf-${def.id}`;
  const label = (
    <Label htmlFor={id}>
      {def.label}
      {def.required && <span className="ml-0.5 text-destructive">*</span>}
    </Label>
  );

  switch (def.field_type) {
    case "textarea":
      return (
        <div className="space-y-2 sm:col-span-2">
          {label}
          <Textarea
            id={id}
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
          />
        </div>
      );
    case "boolean":
      return (
        <div className="flex items-center gap-2">
          <input
            id={id}
            type="checkbox"
            className="h-4 w-4 rounded border-input"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
          />
          {label}
        </div>
      );
    case "number":
      return (
        <div className="space-y-2">
          {label}
          <Input
            id={id}
            type="number"
            value={value === undefined || value === null ? "" : String(value)}
            onChange={(e) =>
              onChange(e.target.value === "" ? "" : Number(e.target.value))
            }
          />
        </div>
      );
    case "date":
      return (
        <div className="space-y-2">
          {label}
          <Input
            id={id}
            type="date"
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
          />
        </div>
      );
    case "select":
      return (
        <div className="space-y-2">
          {label}
          <Select
            id={id}
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
          >
            <option value="">—</option>
            {(def.options ?? []).map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </Select>
        </div>
      );
    case "multiselect": {
      const selected = Array.isArray(value) ? (value as string[]) : [];
      return (
        <div className="space-y-2 sm:col-span-2">
          {label}
          <div className="flex flex-wrap gap-3">
            {(def.options ?? []).map((o) => {
              const checked = selected.includes(o);
              return (
                <label key={o} className="flex items-center gap-1.5 text-sm">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-input"
                    checked={checked}
                    onChange={(e) =>
                      onChange(
                        e.target.checked
                          ? [...selected, o]
                          : selected.filter((x) => x !== o),
                      )
                    }
                  />
                  {o}
                </label>
              );
            })}
          </div>
        </div>
      );
    }
    default:
      // text, url, email
      return (
        <div className="space-y-2">
          {label}
          <Input
            id={id}
            type={def.field_type === "email" ? "email" : def.field_type === "url" ? "url" : "text"}
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
          />
        </div>
      );
  }
}

/**
 * Read-only render of custom field values on a detail page. Mirrors the
 * widget mapping but as label/value rows; skips keys with no value.
 */
export function CustomFieldsDisplay({
  entityType,
  value,
}: {
  entityType: CustomFieldEntity;
  value: Record<string, unknown> | null | undefined;
}) {
  const t = useTranslations("customFields");
  const [defs, setDefs] = useState<CustomFieldDefinition[] | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api
      .listCustomFields(token, entityType)
      .then(setDefs)
      .catch(() => setDefs([]));
  }, [entityType]);

  if (!defs || defs.length === 0) return null;
  const rows = defs.filter((d) => {
    const v = value?.[d.key];
    return v !== undefined && v !== null && v !== "" && !(Array.isArray(v) && v.length === 0);
  });
  if (rows.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">
        {t("sectionTitle")}
      </div>
      <dl className="grid gap-3 sm:grid-cols-2">
        {rows.map((d) => (
          <div key={d.id}>
            <dt className="text-xs uppercase tracking-wider text-muted-foreground">
              {d.label}
            </dt>
            <dd className="mt-1 text-sm">{formatValue(d, value?.[d.key])}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function formatValue(def: CustomFieldDefinition, v: unknown): string {
  if (def.field_type === "boolean") return v ? "✓" : "—";
  if (def.field_type === "multiselect" && Array.isArray(v)) return v.join(", ");
  return String(v ?? "—");
}
