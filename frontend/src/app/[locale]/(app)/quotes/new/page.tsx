"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { QuoteForm } from "@/components/quote-form";
import { api, type QuoteCreate } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function NewQuotePage() {
  const t = useTranslations("quotes");
  const locale = useLocale();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(payload: QuoteCreate) {
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const quote = await api.createQuote(token, payload);
      router.push(`/${locale}/quotes/${quote.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">{t("create")}</h1>
      <QuoteForm submitLabel={t("create")} busy={busy} error={error} onSubmit={create} />
    </div>
  );
}
