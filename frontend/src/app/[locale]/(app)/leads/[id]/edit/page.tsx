"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CustomFieldsInput } from "@/components/custom-fields-input";
import { api, type LeadStage } from "@/lib/api";
import { getToken } from "@/lib/auth";

const STAGES: LeadStage[] = [
  "new",
  "contacted",
  "qualified",
  "proposal_sent",
  "negotiation",
  "won",
  "lost",
];

export default function EditLeadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("leads");
  const tStages = useTranslations("leads.stages");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
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
    company_size: "",
    budget: "",
    source: "",
    notes: "",
    stage: "new" as LeadStage,
  });

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api
      .getLead(token, id)
      .then((l) => {
        setForm({
          first_name: l.first_name ?? "",
          last_name: l.last_name ?? "",
          email: l.email ?? "",
          phone: l.phone ?? "",
          company: l.company ?? "",
          industry: l.industry ?? "",
          country: l.country ?? "",
          company_size: l.company_size?.toString() ?? "",
          budget: l.budget?.toString() ?? "",
          source: l.source ?? "",
          notes: l.notes ?? "",
          stage: l.stage,
        });
        setCustomFields((l.custom_fields as Record<string, unknown>) ?? {});
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  function set<K extends keyof typeof form>(k: K, v: (typeof form)[K]) {
    setForm((s) => ({ ...s, [k]: v }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const payload = {
        first_name: form.first_name,
        last_name: form.last_name,
        email: form.email || null,
        phone: form.phone || null,
        company: form.company || null,
        industry: form.industry || null,
        country: form.country || null,
        company_size: form.company_size ? Number(form.company_size) : null,
        budget: form.budget ? Number(form.budget) : null,
        source: form.source || null,
        notes: form.notes || null,
        stage: form.stage,
        custom_fields: customFields,
      };
      await api.updateLead(token, id, payload);
      router.push(`/${locale}/leads/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">{tCommon("loading")}</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;

  return (
    <Card className="max-w-3xl">
      <CardHeader>
        <CardTitle>
          {tCommon("edit")} — {form.first_name} {form.last_name}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field id="first_name" label={t("firstName")} required value={form.first_name} onChange={(v) => set("first_name", v)} />
          <Field id="last_name" label={t("lastName")} required value={form.last_name} onChange={(v) => set("last_name", v)} />
          <Field id="email" label={t("email")} type="email" value={form.email} onChange={(v) => set("email", v)} />
          <Field id="phone" label={t("phone")} value={form.phone} onChange={(v) => set("phone", v)} />
          <Field id="company" label={t("company")} value={form.company} onChange={(v) => set("company", v)} />
          <Field id="industry" label={t("industry")} value={form.industry} onChange={(v) => set("industry", v)} />
          <Field id="country" label={t("country")} maxLength={2} value={form.country} onChange={(v) => set("country", v.toUpperCase())} />
          <Field id="company_size" label={t("companySize")} type="number" value={form.company_size} onChange={(v) => set("company_size", v)} />
          <Field id="budget" label={t("budget")} type="number" value={form.budget} onChange={(v) => set("budget", v)} />
          <Field id="source" label={t("source")} value={form.source} onChange={(v) => set("source", v)} />
          <div className="space-y-2">
            <Label htmlFor="stage">{t("stage")}</Label>
            <Select
              id="stage"
              value={form.stage}
              onChange={(e) => set("stage", e.target.value as LeadStage)}
            >
              {STAGES.map((s) => (
                <option key={s} value={s}>{tStages(s)}</option>
              ))}
            </Select>
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
            entityType="lead"
            value={customFields}
            onChange={setCustomFields}
          />
          {error && <p className="text-sm text-destructive sm:col-span-2">{error}</p>}
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" disabled={busy}>{t("save")}</Button>
            <Button type="button" variant="ghost" onClick={() => router.push(`/${locale}/leads/${id}`)}>
              {t("cancel")}
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
