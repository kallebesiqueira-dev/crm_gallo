"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Plus, ScrollText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api, type Contract } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { STATUS_VARIANT } from "./status";

export default function ContractsPage() {
  const t = useTranslations("contracts");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const [contracts, setContracts] = useState<Contract[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api
      .listContracts(token)
      .then((page) => {
        setContracts(page.items);
        setCursor(page.next_cursor);
        setHasMore(page.has_more);
      })
      .catch(() => setContracts([]));
  }, []);

  async function loadMore() {
    const token = getToken();
    if (!token || !cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await api.listContracts(token, { cursor });
      setContracts((prev) => [...(prev ?? []), ...page.items]);
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
          <Link href={`/${locale}/contracts/new`}>
            <Plus className="h-4 w-4" />
            {t("new")}
          </Link>
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          {contracts === null ? (
            <div className="p-10 text-center text-sm text-muted-foreground">…</div>
          ) : contracts.length === 0 ? (
            <div className="p-10 text-center text-sm text-muted-foreground">{t("empty")}</div>
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
