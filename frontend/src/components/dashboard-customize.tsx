"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Check, ChevronDown, Settings2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * The dashboard "Customize" control: a dropdown that toggles the visibility of
 * the main dashboard sections. State is owned by the dashboard (persisted to
 * localStorage there); this component just renders the menu.
 */
export function DashboardCustomize({
  items,
  hidden,
  onToggle,
}: {
  items: { key: string; label: string }[];
  hidden: Set<string>;
  onToggle: (key: string) => void;
}) {
  const t = useTranslations("dashboard");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium text-foreground shadow-sm transition hover:border-primary/40"
      >
        <Settings2 className="h-4 w-4 text-primary" />
        {t("customize")}
        <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-1.5 w-60 rounded-lg border bg-popover p-1.5 text-popover-foreground shadow-xl">
          <div className="px-2 py-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {t("customizeHint")}
          </div>
          {items.map((it) => {
            const visible = !hidden.has(it.key);
            return (
              <button
                key={it.key}
                type="button"
                onClick={() => onToggle(it.key)}
                className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm transition hover:bg-accent"
              >
                <span
                  className={cn(
                    "grid h-4 w-4 shrink-0 place-items-center rounded border transition",
                    visible ? "border-primary bg-primary text-primary-foreground" : "border-input",
                  )}
                >
                  {visible && <Check className="h-3 w-3" />}
                </span>
                <span className="flex-1 truncate">{it.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
