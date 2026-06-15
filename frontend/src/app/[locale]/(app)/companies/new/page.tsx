"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CustomFieldsInput } from "@/components/custom-fields-input";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function NewCompanyPage() {
  const t = useTranslations("companies");
  const tLeads = useTranslations("leads");
  const locale = useLocale();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customFields, setCustomFields] = useState<Record<string, unknown>>({});
  const [form, setForm] = useState({
    name: "",
    industry: "",
    website: "",
    phone: "",
    email: "",
    country: "",
    address: "",
    size: "",
    notes: "",
  });

  function set<K extends keyof typeof form>(k: K, v: string) {
    setForm((s) => ({ ...s, [k]: v }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const payload: Record<string, string | number | null> = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, v || null]),
      );
      payload.name = form.name;
      payload.size = form.size ? Number(form.size) : null;
      const company = await api.createCompany(token, {
        ...payload,
        custom_fields: customFields,
      });
      router.push(`/${locale}/companies/${company.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="max-w-3xl">
      <CardHeader>
        <CardTitle>{t("new")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field id="name" label={t("name")} required value={form.name} onChange={(v) => set("name", v)} />
          <Field id="industry" label={t("industry")} value={form.industry} onChange={(v) => set("industry", v)} />
          <Field id="website" label={t("website")} value={form.website} onChange={(v) => set("website", v)} />
          <Field id="email" label={t("email")} type="email" value={form.email} onChange={(v) => set("email", v)} />
          <Field id="phone" label={t("phone")} value={form.phone} onChange={(v) => set("phone", v)} />
          <Field id="country" label={t("country")} maxLength={2} value={form.country} onChange={(v) => set("country", v.toUpperCase())} />
          <Field id="size" label={t("size")} type="number" value={form.size} onChange={(v) => set("size", v)} />
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="address">{t("address")}</Label>
            <Input id="address" value={form.address} onChange={(e) => set("address", e.target.value)} />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="notes">{t("notes")}</Label>
            <Textarea
              id="notes"
              className="min-h-[100px]"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
            />
          </div>
          <CustomFieldsInput
            entityType="company"
            value={customFields}
            onChange={setCustomFields}
          />
          {error && <p className="text-sm text-destructive sm:col-span-2">{error}</p>}
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" disabled={busy}>{tLeads("save")}</Button>
            <Button type="button" variant="ghost" onClick={() => router.push(`/${locale}/companies`)}>
              {tLeads("cancel")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function Field(props: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  maxLength?: number;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={props.id}>{props.label}</Label>
      <Input
        id={props.id}
        type={props.type}
        required={props.required}
        maxLength={props.maxLength}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
      />
    </div>
  );
}
