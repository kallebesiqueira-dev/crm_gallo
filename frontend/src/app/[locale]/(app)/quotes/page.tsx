"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { FileText, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { api, type Quote } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { STATUS_VARIANT } from "./status";

export default function QuotesPage() {
  const t = useTranslations("quotes");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const [quotes, setQuotes] = useState<Quote[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api
      .listQuotes(token)
      .then((page) => {
        setQuotes(page.items);
        setCursor(page.next_cursor);
        setHasMore(page.has_more);
      })
      .catch(() => setQuotes([]));
  }, []);

  async function loadMore() {
    const token = getToken();
    if (!token || !cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await api.listQuotes(token, { cursor });
      setQuotes((prev) => [...(prev ?? []), ...page.items]);
      setCursor(page.next_cursor);
      setHasMore(page.has_more);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <Button asChild size="sm">
          <Link href={`/${locale}/quotes/new`}>
            <Plus className="h-4 w-4" />
            {t("new")}
          </Link>
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          {quotes === null ? (
            <div className="p-10 text-center text-sm text-muted-foreground">…</div>
          ) : quotes.length === 0 ? (
            <EmptyState
              icon={FileText}
              title={t("empty")}
              actionLabel={t("new")}
              actionHref={`/${locale}/quotes/new`}
            />
          ) : (
            <ul className="divide-y">
              {quotes.map((q) => (
                <li key={q.id}>
                  <Link
                    href={`/${locale}/quotes/${q.id}`}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-muted/30"
                  >
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{q.title}</div>
                      <div className="text-xs text-muted-foreground">
                        {q.number} · {t("version", { n: q.version })}
                      </div>
                    </div>
                    <div className="text-sm tabular-nums">
                      {q.currency} {q.total.toFixed(2)}
                    </div>
                    <Badge variant={STATUS_VARIANT[q.status]}>{t(`statuses.${q.status}`)}</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {hasMore && (
        <div className="flex justify-center">
          <Button type="button" variant="outline" size="sm" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? tCommon("loading") : tCommon("loadMore")}
          </Button>
        </div>
      )}
    </div>
  );
}
