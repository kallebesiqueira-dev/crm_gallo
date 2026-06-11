import Link from "next/link";
import { Inbox, Plus, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Shared empty-state for list pages: a friendly icon + message + an optional
 * "create the first one" CTA. Action-first per the product vision — an empty
 * list should point the user at the next step, not just say "nothing here".
 * Reuses each page's existing `empty` + `new` i18n strings (no new keys).
 */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  ctaLabel,
  ctaHref,
}: {
  icon?: LucideIcon;
  title: string;
  ctaLabel?: string;
  ctaHref?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
      <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
        <Icon className="h-6 w-6" />
      </span>
      <p className="max-w-xs text-sm text-muted-foreground">{title}</p>
      {ctaLabel && ctaHref && (
        <Button asChild size="sm" className="mt-1 gap-1.5">
          <Link href={ctaHref}>
            <Plus className="h-4 w-4" />
            {ctaLabel}
          </Link>
        </Button>
      )}
    </div>
  );
}
