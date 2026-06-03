"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import {
  BarChart3,
  Calendar,
  CreditCard,
  FileSignature,
  FileText,
  LayoutDashboard,
  MessagesSquare,
  Settings,
  Sparkles,
  ScrollText,
  Target,
  Trash2,
  Users,
  Workflow,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/logo";

const NAV = [
  { href: "dashboard", label: "dashboard", icon: LayoutDashboard },
  { href: "leads", label: "leads", icon: Target },
  { href: "customers", label: "customers", icon: Users },
  { href: "pipeline", label: "pipeline", icon: Workflow },
  { href: "tasks", label: "tasks", icon: MessagesSquare },
  { href: "calendar", label: "calendar", icon: Calendar },
  { href: "quotes", label: "quotes", icon: FileText },
  { href: "contracts", label: "contracts", icon: FileSignature },
  { href: "assistant", label: "assistant", icon: Sparkles },
  { href: "reports", label: "reports", icon: BarChart3 },
  { href: "billing", label: "billing", icon: CreditCard },
  { href: "trash", label: "trash", icon: Trash2 },
  // `audit` is admin/manager-only on the backend (403 for sales_agent).
  // We don't role-gate the sidebar link in v1 — a sales_agent landing
  // on the page sees a friendly "forbidden" message. Adding a server-
  // side role check to the sidebar would need to wait on the user
  // load, which causes layout flash.
  { href: "audit", label: "audit", icon: ScrollText },
  { href: "settings", label: "settings", icon: Settings },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const locale = useLocale();
  const tNav = useTranslations("nav");
  const tApp = useTranslations("app");

  return (
    <aside className="hidden w-64 shrink-0 border-r bg-card md:flex md:flex-col">
      <div className="border-b px-6 py-5">
        <div className="flex items-center gap-2.5">
          <Logo size="md" iconOnly priority={false} />
          <div>
            <div className="text-sm font-semibold tracking-tight">{tApp("name")}</div>
            <div className="text-xs text-muted-foreground">{tApp("tagline")}</div>
          </div>
        </div>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV.map(({ href, label, icon: Icon }) => {
          const fullPath = `/${locale}/${href}`;
          const active = pathname === fullPath || pathname?.startsWith(`${fullPath}/`);
          return (
            <Link
              key={href}
              href={fullPath}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {tNav(label)}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
