"use client";

import { useRef } from "react";
import { useTranslations } from "next-intl";
import { X } from "lucide-react";
import { useFocusTrap } from "@/lib/use-focus-trap";

// Each row: the keys to render as <kbd> + the description i18n key.
const SHORTCUTS: { keys: string[]; descKey: "search" | "goto" | "help" | "close" }[] = [
  { keys: ["⌘", "K"], descKey: "search" },
  { keys: ["G"], descKey: "goto" },
  { keys: ["?"], descKey: "help" },
  { keys: ["Esc"], descKey: "close" },
];

/** Keyboard-shortcuts cheatsheet, opened with "?" (see the app layout). */
export function ShortcutsHelp({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useTranslations("shortcuts");
  const dialogRef = useRef<HTMLDivElement>(null);

  useFocusTrap(dialogRef, open, { onEscape: onClose });

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] grid place-items-center bg-black/50 p-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={dialogRef}
        className="w-full max-w-sm rounded-xl border bg-background p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold">{t("title")}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("close")}
            className="text-muted-foreground transition hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <ul className="space-y-2.5">
          {SHORTCUTS.map((s) => (
            <li key={s.descKey} className="flex items-center justify-between gap-4 text-sm">
              <span className="text-muted-foreground">{t(s.descKey)}</span>
              <span className="flex shrink-0 gap-1">
                {s.keys.map((k) => (
                  <kbd
                    key={k}
                    className="rounded border border-border bg-muted px-1.5 py-0.5 text-[11px] font-medium"
                  >
                    {k}
                  </kbd>
                ))}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-muted-foreground">{t("hint")}</p>
      </div>
    </div>
  );
}
