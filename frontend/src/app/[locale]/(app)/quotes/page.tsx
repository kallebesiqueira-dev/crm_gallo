"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { FileText, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { useQuotesInfinite } from "@/lib/use-quotes";
import { STATUS_VARIANT } from "./status";

export default function QuotesPage() {
  const t = useTranslations("quotes");
  const tCommon = useTranslations("common");
  const locale = useLocale();

  const quotesQuery = useQuotesInfinite();
  const quotes = useMemo(
    () => quotesQuery.data?.pages.flatMap((p) => p.items),
    [quotesQuery.data],
  );
  const error = quotesQuery.isError ? (quotesQuery.error as Error).message : null;

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

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          {quotesQuery.isLoading ? (
            <div className="grid place-items-center py-10">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !quotes || quotes.length === 0 ? (
            error ? null : (
              <EmptyState
                icon={FileText}
                title={t("empty")}
                actionLabel={t("new")}
                actionHref={`/${locale}/quotes/new`}
              />
            )
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

      {quotesQuery.hasNextPage && (
        <div className="flex justify-center">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => quotesQuery.fetchNextPage()}
            disabled={quotesQuery.isFetchingNextPage}
          >
            {quotesQuery.isFetchingNextPage ? tCommon("loading") : tCommon("loadMore")}
          </Button>
        </div>
      )}
    </div>
  );
}
