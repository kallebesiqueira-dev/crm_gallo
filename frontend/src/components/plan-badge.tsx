"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Briefcase, Crown, Sparkles, Zap } from "lucide-react";
import type { PlanId } from "@/lib/api";
import { cn } from "@/lib/utils";

const PLAN_STYLE: Record<PlanId, { className: string; Icon: typeof Crown }> = {
  free: {
    className:
      "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-300",
    Icon: Sparkles,
  },
  standard: {
    className: "border-primary/30 bg-primary/10 text-primary",
    Icon: Zap,
  },
  business: {
    className:
      "border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300",
    Icon: Briefcase,
  },
  premium: {
    className:
      "border-amber-500/30 bg-gradient-to-r from-amber-500/15 to-fuchsia-500/15 text-amber-700 dark:text-amber-300",
    Icon: Crown,
  },
};

export function PlanBadge({ plan }: { plan: PlanId }) {
  const t = useTranslations("billing");
  const locale = useLocale();
  const { className, Icon } = PLAN_STYLE[plan];
  return (
    <Link
      href={`/${locale}/billing`}
      title={t("currentPlan")}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider transition-all hover:scale-105",
        className,
      )}
    >
      <Icon className="h-3 w-3" />
      {plan}
    </Link>
  );
}
