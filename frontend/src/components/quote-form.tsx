"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Plus, Save, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type Currency, type Product, type Quote, type QuoteCreate } from "@/lib/api";
import { getToken } from "@/lib/auth";

const CURRENCIES: Currency[] = ["EUR", "CHF", "USD", "GBP"];

interface LineRow {
  description: string;
  quantity: number;
  unit_price: number;
  // UI-only helper: which catalog product filled this line (line items
  // carry no product FK server-side — picking just pre-fills the fields).
  product_id?: string;
}

interface Props {
  initial?: Quote;
  submitLabel: string;
  busy?: boolean;
  error?: string | null;
  onSubmit: (payload: QuoteCreate) => void;
}

function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

export function QuoteForm({ initial, submitLabel, busy, error, onSubmit }: Props) {
  const t = useTranslations("quotes");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [currency, setCurrency] = useState<Currency>(initial?.currency ?? "EUR");
  const [taxRate, setTaxRate] = useState<number>(initial?.tax_rate ?? 0);
  const [validUntil, setValidUntil] = useState(initial?.valid_until ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [lines, setLines] = useState<LineRow[]>(
    initial?.line_items.length
      ? initial.line_items.map((li) => ({
          description: li.description,
          quantity: li.quantity,
          unit_price: li.unit_price,
        }))
      : [{ description: "", quantity: 1, unit_price: 0 }],
  );

  // Catalog for the per-line product picker (plan.md §7). Active
  // products only; an empty catalog hides the picker entirely so the
  // form is unchanged for orgs that don't use it.
  const [products, setProducts] = useState<Product[]>([]);
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api
      .listProducts(token, { limit: 200 })
      .then((page) => setProducts(page.items.filter((p) => p.active)))
      .catch(() => {});
  }, []);

  const totals = useMemo(() => {
    const subtotal = round2(lines.reduce((s, l) => s + round2(l.quantity * l.unit_price), 0));
    const tax = round2((subtotal * taxRate) / 100);
    return { subtotal, tax, total: round2(subtotal + tax) };
  }, [lines, taxRate]);

  function updateLine(i: number, patch: Partial<LineRow>) {
    setLines((prev) => prev.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));
  }

  function applyProduct(i: number, productId: string) {
    if (!productId) {
      updateLine(i, { product_id: undefined });
      return;
    }
    const p = products.find((x) => x.id === productId);
    if (!p) return;
    updateLine(i, {
      product_id: p.id,
      description: p.name,
      unit_price: Number(p.price ?? 0),
    });
  }

  function addLine() {
    setLines((prev) => [...prev, { description: "", quantity: 1, unit_price: 0 }]);
  }

  function removeLine(i: number) {
    setLines((prev) => prev.filter((_, idx) => idx !== i));
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const cleaned = lines
      .filter((l) => l.description.trim())
      .map((l, idx) => ({
        description: l.description.trim(),
        quantity: l.quantity,
        unit_price: l.unit_price,
        sort_index: idx,
      }));
    onSubmit({
      title: title.trim(),
      currency,
      tax_rate: taxRate,
      valid_until: validUntil || null,
      notes: notes.trim() || null,
      line_items: cleaned,
    });
  }

  const money = (n: number) => `${currency} ${n.toFixed(2)}`;

  return (
    <form onSubmit={submit} className="space-y-4">
      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("details")}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Label htmlFor="q-title">{t("quoteTitle")}</Label>
            <Input
              id="q-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t("titlePlaceholder")}
              required
            />
          </div>
          <div>
            <Label htmlFor="q-currency">{t("currency")}</Label>
            <Select
              id="q-currency"
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
            <Label htmlFor="q-tax">{t("taxRate")}</Label>
            <Input
              id="q-tax"
              type="number"
              min={0}
              max={100}
              step="0.01"
              value={taxRate}
              onChange={(e) => setTaxRate(Number(e.target.value) || 0)}
            />
          </div>
          <div>
            <Label htmlFor="q-valid">{t("validUntil")}</Label>
            <Input
              id="q-valid"
              type="date"
              value={validUntil ?? ""}
              onChange={(e) => setValidUntil(e.target.value)}
            />
          </div>
          <div className="sm:col-span-2">
            <Label htmlFor="q-notes">{t("notes")}</Label>
            <Textarea
              id="q-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={t("notesPlaceholder")}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("lineItems")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="hidden gap-2 text-xs uppercase tracking-wider text-muted-foreground sm:grid sm:grid-cols-[1fr_5rem_7rem_7rem_2rem]">
            <span>{t("lineDescription")}</span>
            <span>{t("quantity")}</span>
            <span>{t("unitPrice")}</span>
            <span className="text-right">{t("lineTotal")}</span>
            <span />
          </div>
          {lines.map((line, i) => (
            <div
              key={i}
              className="grid gap-2 sm:grid-cols-[1fr_5rem_7rem_7rem_2rem] sm:items-center"
            >
              <div className="flex gap-2">
                {products.length > 0 && (
                  <Select
                    className="w-36 shrink-0"
                    value={line.product_id ?? ""}
                    onChange={(e) => applyProduct(i, e.target.value)}
                    aria-label={t("fromCatalog")}
                  >
                    <option value="">{t("fromCatalog")}</option>
                    {products.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                        {p.sku ? ` · ${p.sku}` : ""}
                      </option>
                    ))}
                  </Select>
                )}
                <Input
                  className="flex-1"
                  value={line.description}
                  onChange={(e) => updateLine(i, { description: e.target.value })}
                  placeholder={t("lineDescription")}
                />
              </div>
              <Input
                type="number"
                min={0}
                step="0.01"
                value={line.quantity}
                onChange={(e) => updateLine(i, { quantity: Number(e.target.value) || 0 })}
              />
              <Input
                type="number"
                min={0}
                step="0.01"
                value={line.unit_price}
                onChange={(e) => updateLine(i, { unit_price: Number(e.target.value) || 0 })}
              />
              <div className="text-sm sm:text-right">{money(round2(line.quantity * line.unit_price))}</div>
              <button
                type="button"
                onClick={() => removeLine(i)}
                className="justify-self-end text-muted-foreground hover:text-destructive"
                aria-label={t("removeLine")}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" onClick={addLine}>
            <Plus className="h-4 w-4" />
            {t("addLine")}
          </Button>

          <div className="ml-auto max-w-xs space-y-1 border-t pt-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t("subtotal")}</span>
              <span>{money(totals.subtotal)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">
                {t("tax")} ({taxRate}%)
              </span>
              <span>{money(totals.tax)}</span>
            </div>
            <div className="flex justify-between font-semibold">
              <span>{t("total")}</span>
              <span>{money(totals.total)}</span>
            </div>
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
