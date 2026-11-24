"use client";

import { useEffect, useState, type ComponentType } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";
import {
  Building2,
  CreditCard,
  Download,
  FileSignature,
  FileText,
  Files,
  Gauge,
  LayoutDashboard,
  MessagesSquare,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  ScrollText,
  Settings,
  Target,
  Trash2,
  Upload,
  Users,
  Users2,
  Workflow,
  CalendarClock,
  ChevronDown,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { WhatsAppIcon } from "@/components/whatsapp-icon";

/**
 * App sidebar — a pinned "home" item followed by six professional groups, on a
 * deep-purple gradient (same in light and dark, per the brand). Item labels use
 * the existing `nav` i18n namespace; the GROUP headers are Italian for now and
 * move to i18n once the shared messages files are free. New entries join their
 * group as each feature ships (e.g. `inbox`/Comunicazioni, added by the
 * WhatsApp work, lives under Lavoro).
 */
type NavItem = { href: string; label: string; icon: LucideIcon | ComponentType<{ className?: string }> };

export const DASHBOARD_ITEM: NavItem = { href: "dashboard", label: "dashboard", icon: LayoutDashboard };

export const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Vendite",
    items: [
      { href: "leads", label: "leads", icon: Target },
      { href: "pipeline", label: "pipeline", icon: Workflow },
      { href: "quotes", label: "quotes", icon: FileText },
      { href: "contracts", label: "contracts", icon: FileSignature },
      { href: "products", label: "products", icon: Package },
      { href: "documents", label: "documents", icon: Files },
    ],
  },
  {
    label: "Clienti",
    items: [
      { href: "customers", label: "customers", icon: Users },
      { href: "companies", label: "companies", icon: Building2 },
    ],
  },
  {
    label: "Lavoro",
    items: [
      { href: "hoje", label: "hoje", icon: CalendarClock },
      { href: "tasks", label: "tasks", icon: MessagesSquare },
      { href: "inbox", label: "inbox", icon: WhatsAppIcon },
    ],
  },
  {
    label: "Crescita",
    items: [
      { href: "imports", label: "imports", icon: Upload },
      { href: "exports", label: "exports", icon: Download },
    ],
  },
  {
    label: "Gestione",
    items: [
      { href: "performance", label: "performance", icon: Gauge },
      { href: "billing", label: "billing", icon: CreditCard },
      { href: "audit", label: "audit", icon: ScrollText },
    ],
  },
  {
    label: "Sistema",
    items: [
      { href: "teams", label: "teams", icon: Users2 },
      { href: "settings", label: "settings", icon: Settings },
      { href: "trash", label: "trash", icon: Trash2 },
    ],
  },
];

// Flat list kept for back-compat (mobile drawer + anything importing NAV).
export const NAV: NavItem[] = [DASHBOARD_ITEM, ...NAV_GROUPS.flatMap((g) => g.items)];

const STORAGE_KEY = "gallo-sidebar-collapsed";

export function Sidebar() {
  const pathname = usePathname();
  const locale = useLocale();
  const tNav = useTranslations("nav");
  const tApp = useTranslations("app");

  const [collapsed, setCollapsed] = useState(false);
  const [closedGroups, setClosedGroups] = useState<Record<string, boolean>>({});
  const [hojePending, setHojePending] = useState(0);

  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(STORAGE_KEY) === "1");
    } catch {
      /* localStorage unavailable — stay expanded */
    }
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.getHoje(token).then((d) => {
      setHojePending(
        d.overdue_deals.length +
          d.today_deals.length +
          d.no_action_deals.length +
          d.overdue_tasks.length +
          d.today_tasks.length,
      );
    }).catch(() => {});
  }, []);

  function toggle() {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        /* ignore persistence failures */
      }
      return next;
    });
  }

  function renderItem({ href, label, icon: Icon }: NavItem, badge?: number) {
    const full = `/${locale}/${href}`;
    const active = pathname === full || pathname?.startsWith(`${full}/`);
    return (
      <Link
        key={href}
        href={full}
        title={collapsed ? tNav(label) : undefined}
        aria-label={collapsed ? tNav(label) : undefined}
        className={cn(
          "group relative flex items-center rounded-md py-1 text-[13px] font-medium transition-colors",
          collapsed ? "justify-center px-2" : "gap-2 px-2",
          active
            ? "bg-white/15 text-white shadow-sm"
            : "text-violet-100/70 hover:bg-white/10 hover:text-white",
        )}
      >
        {active && !collapsed && (
          <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-white" />
        )}
        <Icon className="h-4 w-4 shrink-0" />
        {!collapsed && <span className="truncate">{tNav(label)}</span>}
        {badge && badge > 0 ? (
          collapsed ? (
            <span className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[9px] font-bold text-white">
              {badge > 99 ? "99" : badge}
            </span>
          ) : (
            <span className="ml-auto flex h-5 min-w-[20px] items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold text-white">
              {badge > 99 ? "99+" : badge}
            </span>
          )
        ) : null}
        {collapsed && (
          <span
            role="tooltip"
            className="pointer-events-none absolute left-full top-1/2 z-[60] ml-2 -translate-y-1/2 whitespace-nowrap rounded-md bg-[hsl(var(--sidebar))] px-2 py-1 text-xs font-medium text-[hsl(var(--sidebar-foreground))] opacity-0 shadow-md ring-1 ring-white/10 transition-opacity duration-150 group-hover:opacity-100"
          >
            {tNav(label)}
          </span>
        )}
      </Link>
    );
  }

  return (
    <aside
      data-tour="nav"
      className={cn(
        "hidden shrink-0 flex-col border-r border-white/10 bg-gradient-to-b from-[hsl(var(--sidebar-from))] via-[hsl(var(--sidebar-via))] to-[hsl(var(--sidebar-to))] text-[hsl(var(--sidebar-foreground))] transition-[width] duration-300 ease-in-out md:flex",
        collapsed ? "w-14" : "w-52",
      )}
    >
      {/* Brand */}
      <div
        className={cn(
          "flex items-center border-b border-white/10",
          collapsed ? "justify-center px-2 py-2.5" : "gap-2 px-3 py-2.5",
        )}
      >
        <Link
          href={`/${locale}/dashboard`}
          aria-label={tApp("name")}
          className={cn("flex items-center", collapsed ? "" : "gap-2.5")}
        >
          <Image
            src="/gallo-logo.png"
            alt=""
            width={48}
            height={48}
            className="h-8 w-8 shrink-0 rounded-md object-contain"
          />
          {!collapsed && (
            <div className="leading-tight">
              <div className="text-sm font-semibold tracking-wide">GALLO</div>
              <div className="text-[10px] font-medium uppercase tracking-wider text-violet-200/55">
                CRM
              </div>
            </div>
          )}
        </Link>
      </div>

      {/* Nav — pinned home, then the six groups */}
      <nav className="flex-1 space-y-2 overflow-y-auto px-2 py-2 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <div>{renderItem(DASHBOARD_ITEM)}</div>
        {NAV_GROUPS.map((group) => {
          const shut = !collapsed && closedGroups[group.label];
          return (
            <div key={group.label}>
              {collapsed ? (
                <div className="mx-2 my-1 h-px bg-white/10" />
              ) : (
                <button
                  type="button"
                  onClick={() =>
                    setClosedGroups((prev) => ({ ...prev, [group.label]: !prev[group.label] }))
                  }
                  className="flex w-full items-center justify-between px-2 pb-0.5 pt-1 text-[10px] font-semibold uppercase tracking-wider text-violet-200/45 hover:text-white"
                >
                  {tNav(`groups.${group.label.toLowerCase()}`)}
                  <ChevronDown className={cn("h-3 w-3 transition", shut && "-rotate-90")} />
                </button>
              )}
              {!shut &&
                group.items.map((item) =>
                  renderItem(item, item.href === "hoje" ? hojePending : undefined),
                )}
            </div>
          );
        })}
      </nav>

      {/* Collapse / expand */}
      <div className="border-t border-white/10 p-2">
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? tApp("expandSidebar") : tApp("collapseSidebar")}
          title={collapsed ? tApp("expandSidebar") : tApp("collapseSidebar")}
          className={cn(
            "flex w-full items-center rounded-md py-1.5 text-[13px] font-medium text-violet-100/70 transition-colors hover:bg-white/10 hover:text-white",
            collapsed ? "justify-center px-2" : "gap-2 px-2",
          )}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4 shrink-0" />
          ) : (
            <>
              <PanelLeftClose className="h-4 w-4 shrink-0" />
              <span className="truncate">{tApp("collapseSidebar")}</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
