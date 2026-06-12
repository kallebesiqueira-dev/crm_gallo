"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle2, Circle, X, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type OnboardingChecklist, type OnboardingStep } from "@/lib/api";

const STEP_LINKS: Record<OnboardingStep["key"], string> = {
  pipeline_ready: "/pipeline",
  first_lead: "/leads/new",
  next_action_set: "/pipeline",
  teammate_invited: "/settings",
  proposal_sent: "/quotes/new",
};

const DISMISSED_KEY = "onboarding_dismissed";

export function OnboardingChecklistWidget({ locale }: { locale: string }) {
  const t = useTranslations("onboarding");
  const [checklist, setChecklist] = useState<OnboardingChecklist | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && localStorage.getItem(DISMISSED_KEY)) {
      setDismissed(true);
      return;
    }
    api.getOnboardingChecklist().then(setChecklist).catch(() => {});
  }, []);

  function dismiss() {
    localStorage.setItem(DISMISSED_KEY, "1");
    setDismissed(true);
  }

  if (dismissed || !checklist || checklist.done) return null;

  return (
    <Card className="border-primary/20 bg-primary/5">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-base">{t("title")}</CardTitle>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {t("completed", { completed: checklist.completed, total: checklist.total })}
            </p>
          </div>
          <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={dismiss}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="mt-2 h-1.5 w-full rounded-full bg-muted">
          <div
            className="h-1.5 rounded-full bg-primary transition-all"
            style={{ width: `${(checklist.completed / checklist.total) * 100}%` }}
          />
        </div>
      </CardHeader>
      <CardContent className="pb-3">
        <ul className="space-y-1.5">
          {checklist.steps.map((step) => (
            <li key={step.key}>
              <a
                href={`/${locale}${STEP_LINKS[step.key]}`}
                className="flex items-center gap-3 rounded-md px-2 py-1.5 hover:bg-muted/60 transition-colors"
              >
                {step.done ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600" />
                ) : (
                  <Circle className="h-4 w-4 shrink-0 text-muted-foreground/50" />
                )}
                <div className="flex-1 min-w-0">
                  <span className={`text-sm ${step.done ? "line-through text-muted-foreground" : "font-medium"}`}>
                    {t(`steps.${step.key}`)}
                  </span>
                  {!step.done && (
                    <p className="text-xs text-muted-foreground truncate">
                      {t(`stepHints.${step.key}`)}
                    </p>
                  )}
                </div>
                {!step.done && <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />}
              </a>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
