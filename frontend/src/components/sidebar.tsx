"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import {
  BarChart3,
  Building2,
  Calendar,
  CopyCheck,
  CreditCard,
  FileSignature,
  FileText,
  Gauge,
  Inbox,
  LayoutDashboard,
  MessagesSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Sparkles,
  ScrollText,
  Target,
  Trash2,
  Upload,
  Users,
  Workflow,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/logo";

export const NAV = [
  { href: "dashboard", label: "dashboard", icon: LayoutDashboard },
  { href: "leads", label: "leads", icon: Target },
  { href: "customers", label: "customers", icon: Users },
  { href: "companies", label: "companies", icon: Building2 },
  { href: "duplicates", label: "duplicates", icon: CopyCheck },
  { href: "forms", label: "forms", icon: Inbox },
  { href: "pipeline", label: "pipeline", icon: Workflow },
  { href: "tasks", label: "tasks", icon: MessagesSquare },
  { href: "calendar", label: "calendar", icon: Calendar },
  { href: "quotes", label: "quotes", icon: FileText },
  { href: "contracts", label: "contracts", icon: FileSignature },
  { href: "assistant", label: "assistant", icon: Sparkles },
  { href: "imports", label: "imports", icon: Upload },
  { href: "reports", label: "reports", icon: BarChart3 },
  { href: "performance", label: "performance", icon: Gauge },
  { href: "automations", label: "automations", icon: Zap },
  { href: "billing", label: "billing", icon: CreditCard },
  // `audit` is admin/manager-only on the backend (403 for sales_agent).
  // We don't role-gate the sidebar link in v1 — a sales_agent landing
  // on the page sees a friendly "forbidden" message. Adding a server-
  // side role check to the sidebar would need to wait on the user
  // load, which causes layout flash.
  { href: "audit", label: "audit", icon: ScrollText },
  // Settings + Trash pinned to the very bottom of the nav.
  { href: "settings", label: "settings", icon: Settings },
  { href: "trash", label: "trash", icon: Trash2 },
] as const;

const STORAGE_KEY = "gallo-sidebar-collapsed";

export function Sidebar() {
  const pathname = usePathname();
  const locale = useLocale();
  const tNav = useTranslations("nav");
  const tApp = useTranslations("app");

  // Hydration-safe: SSR and the first client render both assume expanded
  // (the common default, so markup matches and React doesn't warn), then we
  // sync the real preference from localStorage after mount. Same pattern as
  // ThemeToggle. The width transition makes the post-mount sync look smooth
  // rather than a hard flash.
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(STORAGE_KEY) === "1");
    } catch {
      /* localStorage unavailable (private mode / SSR) — stay expanded */
    }
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

  return (
    <aside
      className={cn(
        "hidden shrink-0 border-r bg-card transition-[width] duration-300 ease-in-out md:flex md:flex-col",
        collapsed ? "w-16" : "w-64",
      )}
    >
      {/* Brand — full lockup when expanded, square mark when collapsed. */}
      <div
        className={cn(
          "flex items-center border-b",
          collapsed ? "justify-center px-2 py-4" : "justify-between px-6 py-5",
        )}
      >
        {collapsed ? (
          <Link href={`/${locale}/dashboard`} aria-label={tApp("name")}>
            <Image
              src="/icon.png"
              alt={tApp("name")}
              width={36}
              height={36}
              priority={false}
              className="h-9 w-9 rounded-lg object-contain"
            />
          </Link>
        ) : (
          <div className="flex flex-col gap-2">
            <Logo size="lg" priority={false} />
            <div className="text-xs text-muted-foreground">{tApp("tagline")}</div>
          </div>
        )}
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV.map(({ href, label, icon: Icon }) => {
          const fullPath = `/${locale}/${href}`;
          const active = pathname === fullPath || pathname?.startsWith(`${fullPath}/`);
          return (
            <Link
              key={href}
              href={fullPath}
              title={collapsed ? tNav(label) : undefined}
              aria-label={collapsed ? tNav(label) : undefined}
              className={cn(
                "group relative flex items-center rounded-md py-2 text-sm font-medium transition-colors",
                collapsed ? "justify-center px-2" : "gap-3 px-3",
                active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {!collapsed && <span className="truncate">{tNav(label)}</span>}
              {/* Collapsed-only hover tooltip — pure Tailwind, no extra dep.
                  z-[60] clears the app header (z-50); the brand-dark popover
                  reads in both themes. */}
              {collapsed && (
                <span
                  role="tooltip"
                  className="pointer-events-none absolute left-full top-1/2 z-[60] ml-2 -translate-y-1/2 whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background opacity-0 shadow-md transition-opacity duration-150 group-hover:opacity-100"
                >
                  {tNav(label)}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Collapse / expand toggle, pinned to the bottom like pro dashboards. */}
      <div className="border-t p-3">
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? tApp("expandSidebar") : tApp("collapseSidebar")}
          title={collapsed ? tApp("expandSidebar") : tApp("collapseSidebar")}
          className={cn(
            "flex w-full items-center rounded-md py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
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
