"use client";

import { type ComponentType, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Building2, Loader2, Plus, Search, User, Users } from "lucide-react";
import { NAV } from "@/components/sidebar";
import { api, type Company, type Customer, type Lead } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { useFocusTrap } from "@/lib/use-focus-trap";
import { cn } from "@/lib/utils";

type Icon = ComponentType<{ className?: string }>;
type CommandItem = { kind: "command"; id: string; label: string; icon: Icon; href: string };
type EntityItem = {
  kind: "entity";
  type: "lead" | "customer" | "company";
  id: string;
  label: string;
  sub?: string;
};
type Item = CommandItem | EntityItem;

const ENTITY_ICON: Record<EntityItem["type"], Icon> = { lead: User, customer: Users, company: Building2 };

// Quick-create commands → each entity's "/new" route.
const CREATE_ROUTES = [
  { id: "new-lead", href: "leads/new", key: "newLead" },
  { id: "new-customer", href: "customers/new", key: "newCustomer" },
  { id: "new-company", href: "companies/new", key: "newCompany" },
  { id: "new-deal", href: "pipeline/new", key: "newDeal" },
  { id: "new-quote", href: "quotes/new", key: "newQuote" },
  { id: "new-contract", href: "contracts/new", key: "newContract" },
  { id: "new-product", href: "products/new", key: "newProduct" },
] as const;

/**
 * ⌘K command palette. Empty query lists every navigation target (the sidebar
 * NAV) plus quick-create actions; typing filters those commands and, at ≥2
 * chars, also searches leads/customers/companies. Arrow keys move the
 * selection, Enter runs it, Escape closes (focus returns to the trigger).
 */
export function GlobalSearch({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useTranslations("search");
  const tNav = useTranslations("nav");
  const router = useRouter();
  const locale = useLocale();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<EntityItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useFocusTrap(dialogRef, open, { onEscape: onClose, initialFocus: inputRef });

  const commands = useMemo<CommandItem[]>(() => {
    const nav: CommandItem[] = NAV.map((n) => ({
      kind: "command",
      id: `nav-${n.href}`,
      label: tNav(n.label),
      icon: n.icon as Icon,
      href: `/${locale}/${n.href}`,
    }));
    const create: CommandItem[] = CREATE_ROUTES.map((c) => ({
      kind: "command",
      id: c.id,
      label: t(c.key),
      icon: Plus,
      href: `/${locale}/${c.href}`,
    }));
    return [...nav, ...create];
  }, [tNav, t, locale]);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 40);
    } else {
      setQ("");
      setResults([]);
    }
  }, [open]);

  // Entity search (leads/customers/companies) for queries ≥ 2 chars.
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
            kind: "entity" as const,
            type: "lead" as const,
            id: l.id,
            label: `${l.first_name} ${l.last_name}`.trim(),
            sub: l.company ?? l.email ?? undefined,
          })),
          ...customers.items.map((c) => ({
            kind: "entity" as const,
            type: "customer" as const,
            id: c.id,
            label: `${c.first_name} ${c.last_name}`.trim(),
            sub: c.company ?? c.email ?? undefined,
          })),
          ...companies.items.map((c) => ({
            kind: "entity" as const,
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

  const query = q.trim().toLowerCase();
  const items = useMemo<Item[]>(() => {
    const cmds = query ? commands.filter((c) => c.label.toLowerCase().includes(query)) : commands;
    return [...cmds, ...results];
  }, [commands, results, query]);

  // Reset + clamp the selection, and keep it scrolled into view.
  useEffect(() => {
    setSelected(0);
  }, [q]);
  useEffect(() => {
    if (selected >= items.length) setSelected(Math.max(0, items.length - 1));
  }, [items.length, selected]);
  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>(`[data-idx="${selected}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  function run(item: Item) {
    if (item.kind === "command") {
      router.push(item.href);
    } else {
      const path =
        item.type === "lead" ? "leads" : item.type === "customer" ? "customers" : "companies";
      router.push(`/${locale}/${path}/${item.id}`);
    }
    onClose();
  }

  function onInputKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelected((i) => Math.min(i + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelected((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const it = items[selected];
      if (it) run(it);
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-black/50 p-4 pt-[12vh]"
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={dialogRef}
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
            onKeyDown={onInputKey}
            placeholder={t("placeholder")}
            aria-label={t("placeholder")}
            className="h-12 flex-1 bg-transparent text-sm outline-none"
          />
          {busy && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        </div>
        <div ref={listRef} className="max-h-[55vh] overflow-y-auto p-1.5">
          {items.length === 0 ? (
            busy ? null : (
              <p className="px-3 py-6 text-center text-sm text-muted-foreground">{t("noResults")}</p>
            )
          ) : (
            items.map((item, idx) => {
              const Icon = item.kind === "command" ? item.icon : ENTITY_ICON[item.type];
              const key = item.kind === "command" ? item.id : `${item.type}-${item.id}`;
              return (
                <button
                  key={key}
                  type="button"
                  data-idx={idx}
                  onClick={() => run(item)}
                  onMouseMove={() => setSelected(idx)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition",
                    idx === selected ? "bg-accent" : "hover:bg-accent/50",
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="flex-1 truncate font-medium">{item.label}</span>
                  {item.kind === "entity" && item.sub && (
                    <span className="shrink-0 truncate text-xs text-muted-foreground">{item.sub}</span>
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
