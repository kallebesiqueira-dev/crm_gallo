"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CustomFieldsInput } from "@/components/custom-fields-input";
import { api, type Currency, type Customer, type DealStage, type TeamMember } from "@/lib/api";
import { getToken } from "@/lib/auth";

const STAGES: DealStage[] = [
  "new",
  "qualified",
  "proposal_sent",
  "negotiation",
  "won",
  "lost",
];
const CURRENCIES: Currency[] = ["EUR", "CHF", "USD", "GBP"];

export default function NewDealPage() {
  const t = useTranslations("pipeline");
  const tLeads = useTranslations("leads");
  const tStages = useTranslations("leads.stages");
  const locale = useLocale();
  const router = useRouter();

  const [customers, setCustomers] = useState<Customer[]>([]);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customFields, setCustomFields] = useState<Record<string, unknown>>({});
  // Whether the user explicitly picked a currency. Untouched → the
  // field is OMITTED from the payload so the backend fills it with
  // the org's default_currency (plan.md §6); sending the visual
  // default ("EUR") would override that.
  const [currencyTouched, setCurrencyTouched] = useState(false);
  const [form, setForm] = useState({
    title: "",
    value: "",
    currency: "EUR" as Currency,
    stage: "new" as DealStage,
    probability: "10",
    expected_close_date: "",
    customer_id: "",
    owner_id: "",
    notes: "",
  });

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.listAllCustomers(token).then(setCustomers).catch(() => setCustomers([]));
    api.listOrgMembers().then(setMembers).catch(() => setMembers([]));
  }, []);

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
        title: form.title,
        value: form.value ? Number(form.value) : 0,
        ...(currencyTouched ? { currency: form.currency } : {}),
        stage: form.stage,
        probability: Number(form.probability),
        expected_close_date: form.expected_close_date || null,
        customer_id: form.customer_id || null,
        owner_id: form.owner_id || null,
        notes: form.notes || null,
        custom_fields: customFields,
      };
      await api.createDeal(token, payload);
      router.push(`/${locale}/pipeline`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>{t("new")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="title">{t("dealTitle")}</Label>
            <Input
              id="title"
              required
              value={form.title}
              onChange={(e) => set("title", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="value">{t("value")}</Label>
            <Input
              id="value"
              type="number"
              min={0}
              step="0.01"
              value={form.value}
              onChange={(e) => set("value", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="currency">{t("currency")}</Label>
            <select
              id="currency"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={form.currency}
              onChange={(e) => {
                setCurrencyTouched(true);
                set("currency", e.target.value as Currency);
              }}
            >
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="stage">{tLeads("stage")}</Label>
            <select
              id="stage"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={form.stage}
              onChange={(e) => set("stage", e.target.value as DealStage)}
            >
              {STAGES.map((s) => (
                <option key={s} value={s}>
                  {tStages(s)}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="probability">{t("probability")} (%)</Label>
            <Input
              id="probability"
              type="number"
              min={0}
              max={100}
              value={form.probability}
              onChange={(e) => set("probability", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="close">{t("expectedClose")}</Label>
            <Input
              id="close"
              type="date"
              value={form.expected_close_date}
              onChange={(e) => set("expected_close_date", e.target.value)}
            />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="customer">{t("customer")}</Label>
            <select
              id="customer"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={form.customer_id}
              onChange={(e) => set("customer_id", e.target.value)}
            >
              <option value="">—</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.first_name} {c.last_name}
                  {c.company ? ` · ${c.company}` : ""}
                </option>
              ))}
            </select>
          </div>
          {members.length > 0 && (
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="owner_id">{tLeads("owner")}</Label>
              <select
                id="owner_id"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={form.owner_id}
                onChange={(e) => set("owner_id", e.target.value)}
              >
                <option value="">— {tLeads("unassigned")} —</option>
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
              className="flex min-h-[100px] w-full rounded-md border border-input bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
            />
          </div>
          <CustomFieldsInput
            entityType="deal"
            value={customFields}
            onChange={setCustomFields}
          />
          {error && <p className="text-sm text-destructive sm:col-span-2">{error}</p>}
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" disabled={busy}>
              {tLeads("save")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => router.push(`/${locale}/pipeline`)}
            >
              {tLeads("cancel")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
