import Link from "next/link";
import { type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  actionLabel?: string;
  actionHref?: string;
}

export function EmptyState({ icon: Icon, title, description, actionLabel, actionHref }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 px-4 text-center">
      <div className="grid h-14 w-14 place-items-center rounded-2xl bg-muted/60">
        <Icon className="h-7 w-7 text-muted-foreground/60" />
      </div>
      <div>
        <p className="text-base font-medium">{title}</p>
        {description && (
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {actionLabel && actionHref && (
        <Button asChild size="sm" className="mt-1">
          <Link href={actionHref}>{actionLabel}</Link>
        </Button>
      )}
    </div>
  );
}
