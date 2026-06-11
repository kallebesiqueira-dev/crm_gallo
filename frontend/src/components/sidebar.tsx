"use client";

import { useEffect, useState, type ComponentType } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";
import {
  BarChart3,
  Bell,
  Building2,
  Calendar,
  CopyCheck,
  CreditCard,
  Download,
  FileSignature,
  FileText,
  Files,
  Gauge,
  Inbox,
  LayoutDashboard,
  MessagesSquare,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  ScrollText,
  Settings,
  Sparkles,
  Target,
  Trash2,
  Upload,
  Users,
  Users2,
  Workflow,
  Zap,
  CalendarClock,
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
      { href: "duplicates", label: "duplicates", icon: CopyCheck },
    ],
  },
  {
    label: "Lavoro",
    items: [
      { href: "hoje", label: "hoje", icon: CalendarClock },
      { href: "tasks", label: "tasks", icon: MessagesSquare },
      { href: "calendar", label: "calendar", icon: Calendar },
      { href: "inbox", label: "inbox", icon: WhatsAppIcon },
      { href: "notifications", label: "notifications", icon: Bell },
    ],
  },
  {
    label: "Crescita",
    items: [
      { href: "forms", label: "forms", icon: Inbox },
      { href: "imports", label: "imports", icon: Upload },
      { href: "exports", label: "exports", icon: Download },
      { href: "automations", label: "automations", icon: Zap },
      { href: "assistant", label: "assistant", icon: Sparkles },
    ],
  },
  {
    label: "Gestione",
    items: [
      { href: "reports", label: "reports", icon: BarChart3 },
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
          "group relative flex items-center rounded-lg py-2 text-sm font-medium transition-colors",
          collapsed ? "justify-center px-2" : "gap-3 px-3",
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
            <span className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white">
              {badge > 99 ? "99" : badge}
            </span>
          ) : (
            <span className="ml-auto flex h-5 min-w-[20px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
              {badge > 99 ? "99+" : badge}
            </span>
          )
        ) : null}
        {collapsed && (
          <span
            role="tooltip"
            className="pointer-events-none absolute left-full top-1/2 z-[60] ml-2 -translate-y-1/2 whitespace-nowrap rounded-md bg-[#1a0f38] px-2 py-1 text-xs font-medium text-white opacity-0 shadow-md transition-opacity duration-150 group-hover:opacity-100"
          >
            {tNav(label)}
          </span>
        )}
      </Link>
    );
  }

  return (
    <aside
      className={cn(
        "hidden shrink-0 flex-col border-r border-white/10 bg-gradient-to-b from-[#3d2080] via-[#2a1559] to-[#190b33] text-white transition-[width] duration-300 ease-in-out md:flex",
        collapsed ? "w-16" : "w-44",
      )}
    >
      {/* Brand */}
      <div
        className={cn(
          "flex items-center border-b border-white/10",
          collapsed ? "justify-center px-2 py-4" : "px-5 py-5",
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
            width={36}
            height={36}
            className="h-9 w-9 shrink-0 rounded-lg object-contain"
          />
          {!collapsed && (
            <div className="leading-tight">
              <div className="bg-gradient-to-r from-white to-violet-200 bg-clip-text text-base font-bold tracking-tight text-transparent">
                GALLO crm
              </div>
              <div className="text-[10px] font-medium uppercase tracking-[0.12em] text-violet-200/50">
                AI Sales Platform
              </div>
            </div>
          )}
        </Link>
      </div>

      {/* Nav — pinned home, then the six groups */}
      <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-4 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <div className="space-y-1">{renderItem(DASHBOARD_ITEM)}</div>
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="space-y-1">
            {collapsed ? (
              <div className="mx-2 my-1.5 h-px bg-white/10" />
            ) : (
              <div className="px-3 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wider text-violet-200/40">
                {tNav(`groups.${group.label.toLowerCase()}`)}
              </div>
            )}
            {group.items.map((item) => renderItem(item, item.href === "hoje" ? hojePending : undefined))}
          </div>
        ))}
      </nav>

      {/* Collapse / expand */}
      <div className="border-t border-white/10 p-3">
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? tApp("expandSidebar") : tApp("collapseSidebar")}
          title={collapsed ? tApp("expandSidebar") : tApp("collapseSidebar")}
          className={cn(
            "flex w-full items-center rounded-lg py-2 text-sm font-medium text-violet-100/70 transition-colors hover:bg-white/10 hover:text-white",
            collapsed ? "justify-center px-2" : "gap-3 px-3",
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
