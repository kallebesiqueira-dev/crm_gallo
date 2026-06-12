"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { FileSignature, FileText, Search } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { api, type Contract, type Quote } from "@/lib/api";
import { getToken } from "@/lib/auth";

/**
 * Documenti = the status hub over quotes + contracts (skills.md §4 rework):
 * group tiles with live counts act as filters, plus type pills and a
 * number/title search. Rows deep-link into the quote/contract detail,
 * which owns PDF generation/download (the PDF is an async worker
 * attachment — not queryable cheaply per row, so it stays off the list).
 */
type DocKind = "quote" | "contract";
type Doc = {
  kind: DocKind;
  id: string;
  number: string;
  title: string;
  status: string;
  value: number;
  currency: string;
  date: string | null;
  created_at: string;
};

type StatusGroup = "draft" | "waiting" | "closed" | "attention";

const GROUP_OF: Record<string, StatusGroup> = {
  draft: "draft",
  sent: "waiting",
  accepted: "closed",
  signed: "closed",
  active: "closed",
  declined: "attention",
  expired: "attention",
  terminated: "attention",
};

const GROUP_STYLE: Record<StatusGroup, { dot: string; ring: string }> = {
  draft: { dot: "bg-muted-foreground", ring: "ring-muted-foreground/40" },
  waiting: { dot: "bg-blue-500", ring: "ring-blue-500/40" },
  closed: { dot: "bg-emerald-500", ring: "ring-emerald-500/40" },
  attention: { dot: "bg-red-500", ring: "ring-red-500/40" },
};

const GROUPS: StatusGroup[] = ["draft", "waiting", "closed", "attention"];

export default function DocumentsPage() {
  const t = useTranslations("documents");
  const tQuoteStatus = useTranslations("quotes.statuses");
  const tContractStatus = useTranslations("contracts.statuses");
  const locale = useLocale();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [kind, setKind] = useState<"all" | DocKind>("all");
  const [group, setGroup] = useState<StatusGroup | null>(null);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    Promise.all([
      api.listQuotes(token, { limit: 100 }).catch(() => ({ items: [] as Quote[] })),
      api.listContracts(token, { limit: 100 }).catch(() => ({ items: [] as Contract[] })),
    ])
      .then(([qs, cs]) => {
        const quotes: Doc[] = qs.items.map((x) => ({
          kind: "quote",
          id: x.id,
          number: x.number,
          title: x.title,
          status: x.status,
          value: x.total,
          currency: x.currency,
          date: x.valid_until,
          created_at: x.created_at,
        }));
        const contracts: Doc[] = cs.items.map((x) => ({
          kind: "contract",
          id: x.id,
          number: x.number,
          title: x.title,
          status: x.status,
          value: x.value,
          currency: x.currency,
          date: x.effective_date,
          created_at: x.created_at,
        }));
        setDocs(
          [...quotes, ...contracts].sort((a, b) => b.created_at.localeCompare(a.created_at)),
        );
      })
      .finally(() => setLoading(false));
  }, []);

  const money = useMemo(() => {
    const cache = new Map<string, Intl.NumberFormat>();
    return (value: number, currency: string) => {
      let fmt = cache.get(currency);
      if (!fmt) {
        fmt = new Intl.NumberFormat(locale, {
          style: "currency",
          currency,
          maximumFractionDigits: 0,
        });
        cache.set(currency, fmt);
      }
      return fmt.format(value);
    };
  }, [locale]);

  const byKind = kind === "all" ? docs : docs.filter((d) => d.kind === kind);

  const counts = useMemo(() => {
    const c: Record<StatusGroup, number> = { draft: 0, waiting: 0, closed: 0, attention: 0 };
    for (const d of byKind) {
      const g = GROUP_OF[d.status];
      if (g) c[g] += 1;
    }
    return c;
  }, [byKind]);

  const needle = q.trim().toLowerCase();
  const shown = byKind.filter(
    (d) =>
      (group === null || GROUP_OF[d.status] === group) &&
      (needle === "" ||
        d.number.toLowerCase().includes(needle) ||
        d.title.toLowerCase().includes(needle)),
  );

  const statusLabel = (d: Doc) =>
    d.kind === "quote" ? tQuoteStatus(d.status) : tContractStatus(d.status);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      {/* Status tiles — click to filter, click again to clear. */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {GROUPS.map((g) => {
          const active = group === g;
          const style = GROUP_STYLE[g];
          return (
            <button
              key={g}
              type="button"
              onClick={() => setGroup(active ? null : g)}
              aria-pressed={active}
              className={cn(
                "rounded-xl border bg-card p-3 text-left transition hover:border-primary/40",
                active && `ring-2 ${style.ring}`,
              )}
            >
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className={cn("h-2 w-2 shrink-0 rounded-full", style.dot)} />
                <span className="truncate">{t(`group.${g}`)}</span>
              </div>
              <div className="mt-1 text-2xl font-bold tabular-nums">{counts[g]}</div>
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1.5">
          {(["all", "quote", "contract"] as const).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setKind(f)}
              className={cn(
                "rounded-full px-3 py-1 text-sm font-medium transition",
                kind === f
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-accent",
              )}
            >
              {t(`filter.${f}`)}
            </button>
          ))}
        </div>
        <div className="relative ml-auto w-full sm:w-64">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("searchPlaceholder")}
            className="h-9 pl-8"
          />
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">{t("loading")}</p>
      ) : shown.length === 0 ? (
        <Card className="p-10 text-center text-sm text-muted-foreground">{t("empty")}</Card>
      ) : (
        <div className="space-y-1.5">
          {shown.map((d) => {
            const Icon = d.kind === "quote" ? FileText : FileSignature;
            const href = `/${locale}/${d.kind === "quote" ? "quotes" : "contracts"}/${d.id}`;
            const g = GROUP_OF[d.status] ?? "draft";
            return (
              <Link
                key={`${d.kind}-${d.id}`}
                href={href}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border bg-card px-4 py-3 transition hover:border-primary/40 hover:shadow-sm"
              >
                <Icon className="h-5 w-5 shrink-0 text-primary" />
                <div className="min-w-0 flex-1 basis-48">
                  <div className="truncate text-sm font-medium">
                    {d.number} · {d.title}
                  </div>
                  <div className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
                    <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", GROUP_STYLE[g].dot)} />
                    <span className="truncate">
                      {t(`kind.${d.kind}`)} · {statusLabel(d)}
                      {d.date ? ` · ${new Date(d.date).toLocaleDateString(locale)}` : ""}
                    </span>
                  </div>
                </div>
                <div className="shrink-0 text-sm font-semibold tabular-nums">
                  {money(d.value, d.currency)}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
