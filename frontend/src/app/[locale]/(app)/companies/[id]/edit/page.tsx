"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CustomFieldsInput } from "@/components/custom-fields-input";
import { AvatarUpload } from "@/components/avatar-upload";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function EditCompanyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("companies");
  const tLeads = useTranslations("leads");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState<number | null>(null);
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

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api
      .getCompany(token, id)
      .then((c) => {
        setForm({
          name: c.name ?? "",
          industry: c.industry ?? "",
          website: c.website ?? "",
          phone: c.phone ?? "",
          email: c.email ?? "",
          country: c.country ?? "",
          address: c.address ?? "",
          size: c.size != null ? String(c.size) : "",
          notes: c.notes ?? "",
        });
        setCustomFields((c.custom_fields as Record<string, unknown>) ?? {});
        setVersion(c.version);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

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
      await api.updateCompany(
        token,
        id,
        { ...payload, custom_fields: customFields },
        version ?? undefined,
      );
      router.push(`/${locale}/companies/${id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 412) {
        setError(tCommon("versionConflict"));
        const fresh = await api.getCompany(token, id).catch(() => null);
        if (fresh) setVersion(fresh.version);
      } else {
        setError(e instanceof Error ? e.message : "Failed");
      }
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">{tCommon("loading")}</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;

  return (
    <Card className="mx-auto max-w-3xl">
      <CardHeader>
        <div className="flex items-center gap-4">
          <AvatarUpload
            entityType="company"
            entityId={id}
            fallback={form.name.slice(0, 2).toUpperCase() || "?"}
            size={64}
          />
          <CardTitle>
            {tCommon("edit")} — {form.name}
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field id="name" label={t("name")} required value={form.name} onChange={(v) => set("name", v)} />
          <Field id="industry" label={t("industry")} value={form.industry} onChange={(v) => set("industry", v)} />
          <Field id="website" label={t("website")} type="text" value={form.website} onChange={(v) => set("website", v)} />
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
            <Button type="button" variant="ghost" onClick={() => router.push(`/${locale}/companies/${id}`)}>
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
