"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Inbox, Loader2, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api, type Lead, type WebForm } from "@/lib/api";
import { getToken } from "@/lib/auth";

/**
 * The web-form lead queue — the "Moduli" channel of the Inbox (skills.md §4
 * rework: Forms → Inbox). Submissions create Leads whose `source` is the
 * form's default_source (or "Web Form"), so the queue is the recent leads
 * carrying one of those sources. Form MANAGEMENT (embed snippet, pause,
 * delete) stays on /forms, reached from the gear button here.
 */
const QUEUE_WINDOW = 100;

export function FormsQueue() {
  const t = useTranslations("inbox");
  const tStages = useTranslations("leads.stages");
  const locale = useLocale();
  const [forms, setForms] = useState<WebForm[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    Promise.all([
      api.listForms(token).catch(() => [] as WebForm[]),
      api
        .listLeads(token, { limit: QUEUE_WINDOW })
        .then((p) => p.items)
        .catch(() => [] as Lead[]),
    ])
      .then(([fs, ls]) => {
        setForms(fs);
        setLeads(ls);
      })
      .finally(() => setLoading(false));
  }, []);

  const queue = useMemo(() => {
    const sources = new Set<string>(["Web Form"]);
    for (const f of forms) {
      if (f.default_source) sources.add(f.default_source);
    }
    return leads.filter((l) => l.source != null && sources.has(l.source));
  }, [forms, leads]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{t("channelForms")}</h1>
          <p className="text-sm text-muted-foreground">{t("formsQueueSubtitle")}</p>
        </div>
        <Button asChild size="sm" variant="outline" className="shrink-0">
          <Link href={`/${locale}/forms`}>
            <Settings2 className="h-4 w-4" />
            {t("manageForms")}
          </Link>
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center p-10 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : queue.length === 0 ? (
        <Card className="flex flex-col items-center gap-3 p-10 text-center text-sm text-muted-foreground">
          <Inbox className="h-6 w-6" />
          {t("formsQueueEmpty")}
          <Button asChild size="sm" variant="outline">
            <Link href={`/${locale}/forms`}>{t("manageForms")}</Link>
          </Button>
        </Card>
      ) : (
        <div className="space-y-1.5">
          {queue.map((l) => (
            <Link
              key={l.id}
              href={`/${locale}/leads/${l.id}`}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border bg-card px-4 py-3 transition hover:border-primary/40 hover:shadow-sm"
            >
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                <Inbox className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1 basis-40">
                <div className="truncate text-sm font-medium">
                  {l.first_name} {l.last_name}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {[l.email, l.company].filter(Boolean).join(" · ") || "—"}
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                {l.source && (
                  <Badge variant="outline" className="max-w-[10rem] truncate text-[10px]">
                    {l.source}
                  </Badge>
                )}
                <Badge variant="secondary" className="text-[10px]">
                  {tStages(l.stage)}
                </Badge>
                <span className="text-[11px] text-muted-foreground">
                  {new Date(l.created_at).toLocaleDateString(locale)}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
