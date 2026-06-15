"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function NewProductPage() {
  const t = useTranslations("products");
  const tLeads = useTranslations("leads");
  const locale = useLocale();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    sku: "",
    type: "product",
    price: "",
    currency: "EUR",
    unit: "",
    description: "",
    active: true,
  });

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
      const product = await api.createProduct(token, {
        name: form.name,
        sku: form.sku || null,
        type: form.type as "product" | "service",
        price: form.price ? form.price : null,
        currency: form.currency || "EUR",
        unit: form.unit || null,
        description: form.description || null,
        active: form.active,
      });
      router.push(`/${locale}/products/${product.id}/edit`);
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
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="name">{t("name")}</Label>
            <Input id="name" required value={form.name} onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="sku">{t("sku")}</Label>
            <Input id="sku" value={form.sku} onChange={(e) => set("sku", e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="type">{t("type")}</Label>
            <Select
              id="type"
              value={form.type}
              onChange={(e) => set("type", e.target.value)}
            >
              <option value="product">{t("typeProduct")}</option>
              <option value="service">{t("typeService")}</option>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="price">{t("price")}</Label>
            <Input
              id="price"
              type="number"
              step="0.01"
              min="0"
              value={form.price}
              onChange={(e) => set("price", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="currency">{t("currency")}</Label>
            <Input
              id="currency"
              maxLength={3}
              value={form.currency}
              onChange={(e) => set("currency", e.target.value.toUpperCase())}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="unit">{t("unit")}</Label>
            <Input id="unit" value={form.unit} onChange={(e) => set("unit", e.target.value)} />
          </div>
          <label className="flex items-center gap-2 self-end pb-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-input"
              checked={form.active}
              onChange={(e) => set("active", e.target.checked)}
            />
            {t("active")}
          </label>
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="description">{t("description")}</Label>
            <Textarea
              id="description"
              className="min-h-[100px]"
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
            />
          </div>
          {error && <p className="text-sm text-destructive sm:col-span-2">{error}</p>}
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" disabled={busy}>
              {tLeads("save")}
            </Button>
            <Button type="button" variant="ghost" onClick={() => router.push(`/${locale}/products`)}>
              {tLeads("cancel")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
