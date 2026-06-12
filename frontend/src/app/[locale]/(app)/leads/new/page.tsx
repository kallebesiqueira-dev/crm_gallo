"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CustomFieldsInput } from "@/components/custom-fields-input";
import { api, type TeamMember } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function NewLeadPage() {
  const t = useTranslations("leads");
  const locale = useLocale();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customFields, setCustomFields] = useState<Record<string, unknown>>({});
  const [members, setMembers] = useState<TeamMember[]>([]);
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
    owner_id: "",
  });

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.listOrgMembers().then(setMembers).catch(() => {});
  }, []);

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
        owner_id: form.owner_id || null,
        custom_fields: customFields,
      };
      const lead = await api.createLead(token, payload);
      router.push(`/${locale}/leads/${lead.id}`);
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
        <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="first_name">First name</Label>
            <Input
              id="first_name"
              required
              value={form.first_name}
              onChange={(e) => set("first_name", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="last_name">Last name</Label>
            <Input
              id="last_name"
              required
              value={form.last_name}
              onChange={(e) => set("last_name", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={form.email}
              onChange={(e) => set("email", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="phone">Phone</Label>
            <Input id="phone" value={form.phone} onChange={(e) => set("phone", e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="company">{t("company")}</Label>
            <Input
              id="company"
              value={form.company}
              onChange={(e) => set("company", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="industry">Industry</Label>
            <Input
              id="industry"
              value={form.industry}
              onChange={(e) => set("industry", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="country">Country (ISO-2)</Label>
            <Input
              id="country"
              maxLength={2}
              value={form.country}
              onChange={(e) => set("country", e.target.value.toUpperCase())}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="company_size">Company size</Label>
            <Input
              id="company_size"
              type="number"
              min={0}
              value={form.company_size}
              onChange={(e) => set("company_size", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="budget">Budget</Label>
            <Input
              id="budget"
              type="number"
              min={0}
              step="0.01"
              value={form.budget}
              onChange={(e) => set("budget", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="source">Source</Label>
            <Input
              id="source"
              value={form.source}
              onChange={(e) => set("source", e.target.value)}
            />
          </div>
          {members.length > 0 && (
            <div className="space-y-2">
              <Label htmlFor="owner_id">{t("owner")}</Label>
              <select
                id="owner_id"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={form.owner_id}
                onChange={(e) => set("owner_id", e.target.value)}
              >
                <option value="">— {t("unassigned")} —</option>
                {members.map((m) => (
                  <option key={String(m.user_id)} value={String(m.user_id)}>
                    {m.full_name} ({m.role})
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="notes">Notes</Label>
            <textarea
              id="notes"
              className="flex min-h-[100px] w-full rounded-md border border-input bg-background p-3 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
            <Button type="submit" disabled={busy}>
              {t("save")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => router.push(`/${locale}/leads`)}
            >
              {t("cancel")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
