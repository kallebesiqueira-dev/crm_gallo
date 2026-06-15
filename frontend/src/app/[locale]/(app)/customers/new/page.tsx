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

export default function NewCustomerPage() {
  const t = useTranslations("customers");
  const tCommon = useTranslations("leads");
  const locale = useLocale();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customFields, setCustomFields] = useState<Record<string, unknown>>({});
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    phone: "",
    company: "",
    industry: "",
    country: "",
    address: "",
    website: "",
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
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, v || null]),
      ) as Record<string, string | null>;
      payload.first_name = form.first_name;
      payload.last_name = form.last_name;
      const customer = await api.createCustomer(token, {
        ...payload,
        custom_fields: customFields,
      });
      router.push(`/${locale}/customers/${customer.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mx-auto max-w-3xl">
      <CardHeader>
        <CardTitle>{t("new")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field id="first_name" label={tCommon("firstName")} required value={form.first_name} onChange={(v) => set("first_name", v)} />
          <Field id="last_name" label={tCommon("lastName")} required value={form.last_name} onChange={(v) => set("last_name", v)} />
          <Field id="email" label={tCommon("email")} type="email" value={form.email} onChange={(v) => set("email", v)} />
          <Field id="phone" label={tCommon("phone")} value={form.phone} onChange={(v) => set("phone", v)} />
          <Field id="company" label={t("company")} value={form.company} onChange={(v) => set("company", v)} />
          <Field id="industry" label={tCommon("industry")} value={form.industry} onChange={(v) => set("industry", v)} />
          <Field id="country" label={tCommon("country")} maxLength={2} value={form.country} onChange={(v) => set("country", v.toUpperCase())} />
          <Field id="website" label={tCommon("website")} type="url" value={form.website} onChange={(v) => set("website", v)} />
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="address">{tCommon("address")}</Label>
            <Input id="address" value={form.address} onChange={(e) => set("address", e.target.value)} />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="notes">{tCommon("notes")}</Label>
            <Textarea
              id="notes"
              className="min-h-[100px]"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
            />
          </div>
          <CustomFieldsInput
            entityType="customer"
            value={customFields}
            onChange={setCustomFields}
          />
          {error && <p className="text-sm text-destructive sm:col-span-2">{error}</p>}
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" disabled={busy}>{tCommon("save")}</Button>
            <Button type="button" variant="ghost" onClick={() => router.push(`/${locale}/customers`)}>
              {tCommon("cancel")}
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
