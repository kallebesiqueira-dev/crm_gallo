"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Building2, Loader2, Search, User, Users } from "lucide-react";
import { api, type Company, type Customer, type Lead } from "@/lib/api";
import { getToken } from "@/lib/auth";

type Result = {
  type: "lead" | "customer" | "company";
  id: string;
  label: string;
  sub?: string;
};

const ICON = { lead: User, customer: Users, company: Building2 };

export function GlobalSearch({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useTranslations("search");
  const router = useRouter();
  const locale = useLocale();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 40);
    else {
      setQ("");
      setResults([]);
    }
  }, [open]);

  useEffect(() => {
    const token = getToken();
    if (!open || !token || q.trim().length < 2) {
      setResults([]);
      return;
    }
    let stop = false;
    setBusy(true);
    const handle = setTimeout(async () => {
      try {
        const [leads, customers, companies] = await Promise.all([
          api.listLeads(token, { q, limit: 5 }).catch(() => ({ items: [] as Lead[] })),
          api.listCustomers(token, { q, limit: 5 }).catch(() => ({ items: [] as Customer[] })),
          api.listCompanies(token, { q, limit: 5 }).catch(() => ({ items: [] as Company[] })),
        ]);
        if (stop) return;
        setResults([
          ...leads.items.map((l) => ({
            type: "lead" as const,
            id: l.id,
            label: `${l.first_name} ${l.last_name}`.trim(),
            sub: l.company ?? l.email ?? undefined,
          })),
          ...customers.items.map((c) => ({
            type: "customer" as const,
            id: c.id,
            label: `${c.first_name} ${c.last_name}`.trim(),
            sub: c.company ?? c.email ?? undefined,
          })),
          ...companies.items.map((c) => ({
            type: "company" as const,
            id: c.id,
            label: c.name,
            sub: c.industry ?? undefined,
          })),
        ]);
      } finally {
        if (!stop) setBusy(false);
      }
    }, 250);
    return () => {
      stop = true;
      clearTimeout(handle);
    };
  }, [q, open]);

  function go(r: Result) {
    const path = r.type === "lead" ? "leads" : r.type === "customer" ? "customers" : "companies";
    router.push(`/${locale}/${path}/${r.id}`);
    onClose();
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-black/50 p-4 pt-[12vh]"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-xl border bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center gap-2 border-b px-3.5">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && onClose()}
            placeholder={t("placeholder")}
            className="h-12 flex-1 bg-transparent text-sm outline-none"
          />
          {busy && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        </div>
        <div className="max-h-[50vh] overflow-y-auto p-1.5">
          {q.trim().length < 2 ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">{t("hint")}</p>
          ) : results.length === 0 && !busy ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">{t("noResults")}</p>
          ) : (
            results.map((r) => {
              const Icon = ICON[r.type];
              return (
                <button
                  key={`${r.type}-${r.id}`}
                  type="button"
                  onClick={() => go(r)}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition hover:bg-accent"
                >
                  <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="flex-1 truncate font-medium">{r.label}</span>
                  {r.sub && (
                    <span className="shrink-0 truncate text-xs text-muted-foreground">{r.sub}</span>
                  )}
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
