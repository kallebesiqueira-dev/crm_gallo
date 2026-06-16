"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Loader2, Plus, ScrollText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { useContractsInfinite } from "@/lib/use-contracts";
import { STATUS_VARIANT } from "./status";

export default function ContractsPage() {
  const t = useTranslations("contracts");
  const tCommon = useTranslations("common");
  const locale = useLocale();

  const contractsQuery = useContractsInfinite();
  const contracts = useMemo(
    () => contractsQuery.data?.pages.flatMap((p) => p.items),
    [contractsQuery.data],
  );
  const error = contractsQuery.isError ? (contractsQuery.error as Error).message : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <Button asChild size="sm">
          <Link href={`/${locale}/contracts/new`}>
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
          {contractsQuery.isLoading ? (
            <div className="grid place-items-center py-10">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !contracts || contracts.length === 0 ? (
            error ? null : (
              <EmptyState
                icon={ScrollText}
                title={t("empty")}
                actionLabel={t("new")}
                actionHref={`/${locale}/contracts/new`}
              />
            )
          ) : (
            <ul className="divide-y">
              {contracts.map((c) => (
                <li key={c.id}>
                  <Link
                    href={`/${locale}/contracts/${c.id}`}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-muted/30"
                  >
                    <ScrollText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{c.title}</div>
                      <div className="text-xs text-muted-foreground">
                        {c.number} · {t("version", { n: c.version })}
                      </div>
                    </div>
                    <div className="text-sm tabular-nums">
                      {c.currency} {c.value.toFixed(2)}
                    </div>
                    <Badge variant={STATUS_VARIANT[c.status]}>{t(`statuses.${c.status}`)}</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {contractsQuery.hasNextPage && (
        <div className="flex justify-center">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => contractsQuery.fetchNextPage()}
            disabled={contractsQuery.isFetchingNextPage}
          >
            {contractsQuery.isFetchingNextPage ? tCommon("loading") : tCommon("loadMore")}
          </Button>
        </div>
      )}
    </div>
  );
}
