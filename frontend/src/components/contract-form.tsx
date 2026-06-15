"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Contract, ContractCreate, Currency } from "@/lib/api";

const CURRENCIES: Currency[] = ["EUR", "CHF", "USD", "GBP"];

interface Props {
  initial?: Contract;
  submitLabel: string;
  busy?: boolean;
  error?: string | null;
  onSubmit: (payload: ContractCreate) => void;
}

export function ContractForm({ initial, submitLabel, busy, error, onSubmit }: Props) {
  const t = useTranslations("contracts");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [currency, setCurrency] = useState<Currency>(initial?.currency ?? "EUR");
  const [value, setValue] = useState<number>(initial?.value ?? 0);
  const [effectiveDate, setEffectiveDate] = useState(initial?.effective_date ?? "");
  const [endDate, setEndDate] = useState(initial?.end_date ?? "");
  const [autoRenew, setAutoRenew] = useState<boolean>(initial?.auto_renew ?? false);
  const [renewalTerm, setRenewalTerm] = useState<number | "">(
    initial?.renewal_term_months ?? "",
  );
  const [body, setBody] = useState(initial?.body ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit({
      title: title.trim(),
      currency,
      value,
      effective_date: effectiveDate || null,
      end_date: endDate || null,
      auto_renew: autoRenew,
      renewal_term_months: autoRenew && renewalTerm !== "" ? Number(renewalTerm) : null,
      body: body.trim() || null,
      notes: notes.trim() || null,
    });
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("details")}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Label htmlFor="c-title">{t("contractTitle")}</Label>
            <Input
              id="c-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t("titlePlaceholder")}
              required
            />
          </div>
          <div>
            <Label htmlFor="c-currency">{t("currency")}</Label>
            <Select
              id="c-currency"
              value={currency}
              onChange={(e) => setCurrency(e.target.value as Currency)}
            >
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="c-value">{t("value")}</Label>
            <Input
              id="c-value"
              type="number"
              min={0}
              step="0.01"
              value={value}
              onChange={(e) => setValue(Number(e.target.value) || 0)}
            />
          </div>
          <div>
            <Label htmlFor="c-effective">{t("effectiveDate")}</Label>
            <Input
              id="c-effective"
              type="date"
              value={effectiveDate ?? ""}
              onChange={(e) => setEffectiveDate(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="c-end">{t("endDate")}</Label>
            <Input
              id="c-end"
              type="date"
              value={endDate ?? ""}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2 sm:col-span-2">
            <input
              id="c-autorenew"
              type="checkbox"
              className="h-4 w-4 rounded border-input"
              checked={autoRenew}
              onChange={(e) => setAutoRenew(e.target.checked)}
            />
            <Label htmlFor="c-autorenew" className="cursor-pointer">
              {t("autoRenew")}
            </Label>
          </div>
          {autoRenew && (
            <div>
              <Label htmlFor="c-renewal">{t("renewalTerm")}</Label>
              <Input
                id="c-renewal"
                type="number"
                min={1}
                max={120}
                step="1"
                value={renewalTerm}
                onChange={(e) =>
                  setRenewalTerm(e.target.value === "" ? "" : Number(e.target.value))
                }
              />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("termsSection")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label htmlFor="c-body">{t("body")}</Label>
            <Textarea
              id="c-body"
              className="min-h-40"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder={t("bodyPlaceholder")}
            />
          </div>
          <div>
            <Label htmlFor="c-notes">{t("notes")}</Label>
            <Textarea
              id="c-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={t("notesPlaceholder")}
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button type="submit" disabled={busy || !title.trim()}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
