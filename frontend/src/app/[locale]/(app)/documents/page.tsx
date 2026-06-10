"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { FileSignature, FileText } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { api, type Contract, type Quote } from "@/lib/api";
import { getToken } from "@/lib/auth";

type Doc = {
  kind: "quote" | "contract";
  id: string;
  number: string;
  title: string;
  status: string;
  value: number;
  date: string | null;
};

const STATUS_DOT: Record<string, string> = {
  accepted: "bg-emerald-500",
  active: "bg-emerald-500",
  signed: "bg-emerald-500",
  sent: "bg-blue-500",
  draft: "bg-muted-foreground",
  declined: "bg-red-500",
  expired: "bg-amber-500",
  terminated: "bg-red-500",
};

export default function DocumentsPage() {
  const t = useTranslations("documents");
  const locale = useLocale();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [filter, setFilter] = useState<"all" | "quote" | "contract">("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    Promise.all([
      api.listQuotes(token, { limit: 50 }).catch(() => ({ items: [] as Quote[] })),
      api.listContracts(token, { limit: 50 }).catch(() => ({ items: [] as Contract[] })),
    ])
      .then(([q, c]) => {
        const quotes: Doc[] = q.items.map((x) => ({
          kind: "quote",
          id: x.id,
          number: x.number,
          title: x.title,
          status: x.status,
          value: x.subtotal + x.tax_amount,
          date: x.valid_until,
        }));
        const contracts: Doc[] = c.items.map((x) => ({
          kind: "contract",
          id: x.id,
          number: x.number,
          title: x.title,
          status: x.status,
          value: x.value,
          date: x.effective_date,
        }));
        setDocs([...quotes, ...contracts]);
      })
      .finally(() => setLoading(false));
  }, []);

  const eur = useMemo(
    () => new Intl.NumberFormat(locale, { style: "currency", currency: "EUR", maximumFractionDigits: 0 }),
    [locale],
  );
  const shown = docs.filter((d) => filter === "all" || d.kind === filter);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {(["all", "quote", "contract"] as const).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={cn(
              "rounded-full px-3 py-1 text-sm font-medium transition",
              filter === f
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-accent",
            )}
          >
            {t(`filter.${f}`)}
          </button>
        ))}
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
            return (
              <Link
                key={`${d.kind}-${d.id}`}
                href={href}
                className="flex items-center gap-3 rounded-lg border bg-card px-4 py-3 transition hover:border-primary/40 hover:shadow-sm"
              >
                <Icon className="h-5 w-5 shrink-0 text-primary" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">
                    {d.number} · {d.title}
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span
                      className={cn("h-1.5 w-1.5 shrink-0 rounded-full", STATUS_DOT[d.status] ?? "bg-muted-foreground")}
                    />
                    {t(`kind.${d.kind}`)} · {d.status}
                    {d.date ? ` · ${new Date(d.date).toLocaleDateString(locale)}` : ""}
                  </div>
                </div>
                <div className="shrink-0 text-sm font-semibold tabular-nums">{eur.format(d.value)}</div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
