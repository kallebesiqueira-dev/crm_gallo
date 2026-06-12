"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { CheckCircle2, ChevronRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/toast-provider";
import { api, type OnboardingTemplate } from "@/lib/api";

export default function OnboardingPage() {
  const t = useTranslations("onboarding");
  const tw = useTranslations("onboarding.wizard");
  const locale = useLocale();
  const toast = useToast();

  const [templates, setTemplates] = useState<OnboardingTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState<string | null>(null);
  const [applied, setApplied] = useState<Set<string>>(new Set());

  useEffect(() => {
    api.listOnboardingTemplates()
      .then(setTemplates)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function apply(slug: string) {
    if (applying) return;
    setApplying(slug);
    try {
      await api.applyOnboardingTemplate(slug);
      setApplied((prev) => new Set(prev).add(slug));
      toast(tw("applied"), "success");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("409") || msg.includes("already")) {
        toast(tw("alreadyApplied"), "error");
      } else {
        toast(msg || "Failed", "error");
      }
    } finally {
      setApplying(null);
    }
  }

  if (loading) {
    return (
      <div className="grid place-items-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{tw("title")}</h1>
        <p className="mt-1 text-muted-foreground">{tw("subtitle")}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {templates.map((tpl) => {
          const isApplied = applied.has(tpl.slug);
          const isBusy = applying === tpl.slug;
          return (
            <Card
              key={tpl.slug}
              className={`transition-colors ${isApplied ? "border-green-500/60 bg-green-50/40 dark:bg-green-950/20" : ""}`}
            >
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="text-base">
                    {tw(`sectors.${tpl.slug}` as Parameters<typeof tw>[0]) ?? tpl.name}
                  </CardTitle>
                  {isApplied && <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600" />}
                </div>
                <p className="text-xs text-muted-foreground">
                  {tpl.stages.length} {tw("stages")}
                </p>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex flex-wrap gap-1.5">
                  {tpl.stages.map((s) => (
                    <Badge
                      key={s.slug}
                      variant={s.is_won ? "default" : s.is_lost ? "danger" : "secondary"}
                      className="text-xs"
                    >
                      {s.name}
                    </Badge>
                  ))}
                </div>
                <Button
                  size="sm"
                  variant={isApplied ? "outline" : "default"}
                  disabled={isBusy || isApplied}
                  onClick={() => apply(tpl.slug)}
                  className="w-full"
                >
                  {isBusy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : isApplied ? (
                    <CheckCircle2 className="h-4 w-4 text-green-600" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                  {isApplied ? tw("applied") : tw("apply")}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="flex justify-end">
        <Button variant="ghost" asChild>
          <a href={`/${locale}/pipeline`}>{t("dismiss")}</a>
        </Button>
      </div>
    </div>
  );
}
