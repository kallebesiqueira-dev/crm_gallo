"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { QuoteForm } from "@/components/quote-form";
import { PageSpinner } from "@/components/page-spinner";
import { api, type Quote, type QuoteCreate } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function EditQuotePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("quotes");
  const locale = useLocale();
  const router = useRouter();
  const [quote, setQuote] = useState<Quote | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.getQuote(token, id).then(setQuote).catch((e) => setError(String(e)));
  }, [id]);

  async function save(payload: QuoteCreate) {
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await api.updateQuote(token, id, payload);
      router.push(`/${locale}/quotes/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
      setBusy(false);
    }
  }

  if (error && !quote) return <p className="text-sm text-destructive">{error}</p>;
  if (!quote) return <PageSpinner />;

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">
        {t("edit")} · {quote.number} {t("version", { n: quote.version })}
      </h1>
      <QuoteForm initial={quote} submitLabel={t("save")} busy={busy} error={error} onSubmit={save} />
    </div>
  );
}
