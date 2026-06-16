"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { NAV } from "@/components/sidebar";

/**
 * Mobile navigation — a slide-in drawer + hamburger, shown only below `md`
 * (the desktop Sidebar is `hidden md:flex`). Reuses the same NAV source of
 * truth as the sidebar so the two never drift. Closes on navigation, backdrop
 * click and Esc; locks background scroll while open.
 *
 * The drawer is rendered through a portal to `document.body` on purpose: the
 * top bar it lives in uses `backdrop-blur`, which makes that ancestor a
 * containing block for `position: fixed` — without the portal the `fixed
 * inset-0` overlay would be trapped inside the 64px-tall header instead of
 * covering the viewport.
 */
export function MobileNav() {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const pathname = usePathname();
  const locale = useLocale();
  const tNav = useTranslations("nav");
  const tApp = useTranslations("app");

  useEffect(() => setMounted(true), []);

  // Close on route change.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Esc to close + lock background scroll while the drawer is open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open navigation menu"
        aria-expanded={open}
        className="-ml-1 grid h-9 w-9 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground md:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      {mounted &&
        open &&
        createPortal(
          <div
            className="fixed inset-0 z-[90] h-[100dvh] md:hidden"
            role="dialog"
            aria-modal="true"
            aria-label={tApp("name")}
          >
            <div
              className="absolute inset-0 bg-foreground/40 backdrop-blur-sm"
              onClick={() => setOpen(false)}
              aria-hidden="true"
            />
            <div className="absolute inset-y-0 left-0 flex w-72 max-w-[82vw] flex-col border-r bg-card shadow-xl">
              <div className="flex items-center justify-between border-b px-4 py-4 pt-[max(1rem,env(safe-area-inset-top))]">
                <Link
                  href={`/${locale}/dashboard`}
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-2"
                  aria-label={tApp("name")}
                >
                  <Image
                    src="/gallo-logo.png"
                    alt={tApp("name")}
                    width={32}
                    height={32}
                    className="h-8 w-8 rounded-lg object-contain"
                  />
                  <span className="text-sm font-semibold">GALLO CRM</span>
                </Link>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Close menu"
                  className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <nav className="flex-1 space-y-1 overflow-y-auto px-3 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
                {NAV.map(({ href, label, icon: Icon }) => {
                  const fullPath = `/${locale}/${href}`;
                  const active = pathname === fullPath || pathname?.startsWith(`${fullPath}/`);
                  return (
                    <Link
                      key={href}
                      href={fullPath}
                      onClick={() => setOpen(false)}
                      className={cn(
                        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                        active
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:bg-accent hover:text-foreground",
                      )}
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      <span className="truncate">{tNav(label)}</span>
                    </Link>
                  );
                })}
              </nav>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
