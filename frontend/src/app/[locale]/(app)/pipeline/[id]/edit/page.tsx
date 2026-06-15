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

export default function EditDealPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("pipeline");
  const tLeads = useTranslations("leads");
  const tStages = useTranslations("leads.stages");
  const locale = useLocale();
  const router = useRouter();

  const [customers, setCustomers] = useState<Customer[]>([]);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState<number | undefined>(undefined);
  const [customFields, setCustomFields] = useState<Record<string, unknown>>({});
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
    Promise.all([
      api.getDeal(token, id),
      api.listAllCustomers(token).catch(() => [] as Customer[]),
      api.listOrgMembers().catch(() => [] as TeamMember[]),
    ]).then(([deal, custs, mems]) => {
      setForm({
        title: deal.title,
        value: String(deal.value),
        currency: deal.currency,
        stage: deal.stage,
        probability: String(deal.probability),
        expected_close_date: deal.expected_close_date ?? "",
        customer_id: deal.customer_id ?? "",
        owner_id: deal.owner_id ?? "",
        notes: deal.notes ?? "",
      });
      setVersion(deal.version);
      setCustomFields(deal.custom_fields ?? {});
      setCustomers(custs);
      setMembers(mems);
      setLoading(false);
    }).catch((e) => {
      setError(e instanceof Error ? e.message : "Failed to load");
      setLoading(false);
    });
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
      await api.updateDeal(
        token,
        id,
        {
          title: form.title,
          value: Number(form.value) || 0,
          currency: form.currency,
          stage: form.stage,
          probability: Number(form.probability),
          expected_close_date: form.expected_close_date || null,
          customer_id: form.customer_id || null,
          owner_id: form.owner_id || null,
          notes: form.notes || null,
          custom_fields: customFields,
        },
        version,
      );
      router.push(`/${locale}/pipeline/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="grid place-items-center py-20 text-muted-foreground">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-foreground" />
      </div>
    );
  }

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>{t("dealTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
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
            <Select
              id="currency"
              value={form.currency}
              onChange={(e) => set("currency", e.target.value as Currency)}
            >
              {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="stage">{t("stage")}</Label>
            <Select
              id="stage"
              value={form.stage}
              onChange={(e) => set("stage", e.target.value as DealStage)}
            >
              {STAGES.map((s) => <option key={s} value={s}>{tStages(s)}</option>)}
            </Select>
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
            <Select
              id="customer"
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
            </Select>
          </div>
          {members.length > 0 && (
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="owner_id">{tLeads("owner")}</Label>
              <Select
                id="owner_id"
                value={form.owner_id}
                onChange={(e) => set("owner_id", e.target.value)}
              >
                <option value="">— {tLeads("unassigned")} —</option>
                {members.map((m) => (
                  <option key={String(m.user_id)} value={String(m.user_id)}>
                    {m.full_name} ({m.role})
                  </option>
                ))}
              </Select>
            </div>
          )}
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="notes">{tLeads("notes")}</Label>
            <Textarea
              id="notes"
              className="min-h-[100px]"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
            />
          </div>
          <CustomFieldsInput entityType="deal" value={customFields} onChange={setCustomFields} />
          {error && <p className="text-sm text-destructive sm:col-span-2">{error}</p>}
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" disabled={busy}>{tLeads("save")}</Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => router.push(`/${locale}/pipeline/${id}`)}
            >
              {tLeads("cancel")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
