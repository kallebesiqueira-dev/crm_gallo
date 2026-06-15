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

export default function EditCustomerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("customers");
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

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api
      .getCustomer(token, id)
      .then((c) => {
        setForm({
          first_name: c.first_name ?? "",
          last_name: c.last_name ?? "",
          email: c.email ?? "",
          phone: c.phone ?? "",
          company: c.company ?? "",
          industry: c.industry ?? "",
          country: c.country ?? "",
          address: c.address ?? "",
          website: c.website ?? "",
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
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, v || null]),
      ) as Record<string, string | null>;
      payload.first_name = form.first_name;
      payload.last_name = form.last_name;
      await api.updateCustomer(
        token,
        id,
        { ...payload, custom_fields: customFields },
        version ?? undefined,
      );
      router.push(`/${locale}/customers/${id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 412) {
        // Someone edited this record since we loaded it. Reload the
        // latest so the user can re-apply their change on top.
        setError(tCommon("versionConflict"));
        const fresh = await api.getCustomer(token, id).catch(() => null);
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
    <Card className="max-w-3xl">
      <CardHeader>
        <div className="flex items-center gap-4">
          <AvatarUpload
            entityType="customer"
            entityId={id}
            fallback={((form.first_name[0] ?? "") + (form.last_name[0] ?? "")).toUpperCase() || "?"}
            size={64}
          />
          <CardTitle>
            {tCommon("edit")} — {form.first_name} {form.last_name}
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field id="first_name" label={tLeads("firstName")} required value={form.first_name} onChange={(v) => set("first_name", v)} />
          <Field id="last_name" label={tLeads("lastName")} required value={form.last_name} onChange={(v) => set("last_name", v)} />
          <Field id="email" label={tLeads("email")} type="email" value={form.email} onChange={(v) => set("email", v)} />
          <Field id="phone" label={tLeads("phone")} value={form.phone} onChange={(v) => set("phone", v)} />
          <Field id="company" label={t("company")} value={form.company} onChange={(v) => set("company", v)} />
          <Field id="industry" label={tLeads("industry")} value={form.industry} onChange={(v) => set("industry", v)} />
          <Field id="country" label={tLeads("country")} maxLength={2} value={form.country} onChange={(v) => set("country", v.toUpperCase())} />
          <Field id="website" label={tLeads("website")} type="url" value={form.website} onChange={(v) => set("website", v)} />
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="address">{tLeads("address")}</Label>
            <Input id="address" value={form.address} onChange={(e) => set("address", e.target.value)} />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="notes">{tLeads("notes")}</Label>
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
            <Button type="submit" disabled={busy}>{tLeads("save")}</Button>
            <Button type="button" variant="ghost" onClick={() => router.push(`/${locale}/customers/${id}`)}>
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
