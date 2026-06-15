"use client";

import { useTranslations } from "next-intl";
import { ArrowUp, Sparkles } from "lucide-react";

// Mirrors the chips in <AssistantPanel>; kept in sync intentionally.
const CHIPS = [
  { id: "pipeline", labelKey: "chipPipeline", promptKey: "promptPipeline" },
  { id: "proposal", labelKey: "chipProposal", promptKey: "promptProposal" },
  { id: "report", labelKey: "chipReport", promptKey: "promptReport" },
  { id: "customers", labelKey: "chipCustomers", promptKey: "promptCustomers" },
  { id: "email", labelKey: "chipEmail", promptKey: "promptEmail" },
] as const;

/** Open the global assistant sheet (the app layout listens for this). */
function openAssistant(prompt: string) {
  window.dispatchEvent(new CustomEvent("gallo:assistant-open", { detail: { prompt } }));
}

/**
 * Dashboard AI entry card (skills.md §3 priority A) — a compact "smart card":
 * brand-gradient greeting + a faux composer + quick-action chips. Tapping the
 * composer opens the assistant bottom-sheet/panel; tapping a chip opens it AND
 * sends that prompt. Colors follow the project tokens + the brand gradient.
 */
export function AssistantCard() {
  const t = useTranslations("assistant");
  return (
    <div className="rounded-2xl border bg-card p-4 shadow-sm sm:p-5">
      <div className="flex items-center gap-2">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
          <Sparkles className="h-4 w-4" />
        </span>
        <h2 className="bg-gradient-to-r from-violet-600 to-fuchsia-500 bg-clip-text text-lg font-bold tracking-tight text-transparent dark:from-white dark:to-violet-200">
          {t("hero")}
        </h2>
      </div>
      <button
        type="button"
        onClick={() => openAssistant("")}
        className="mt-3 flex w-full items-center justify-between gap-2 rounded-xl border border-input bg-background px-3.5 py-2.5 text-left text-sm text-muted-foreground transition hover:border-primary/40"
      >
        <span className="truncate">{t("placeholder")}</span>
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground">
          <ArrowUp className="h-4 w-4" />
        </span>
      </button>
      <div className="mt-3 flex flex-wrap gap-2">
        {CHIPS.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => openAssistant(t(c.promptKey))}
            className="rounded-full border border-border bg-muted/40 px-3 py-1.5 text-xs font-medium text-foreground/80 transition hover:border-primary/40 hover:text-foreground"
          >
            {t(c.labelKey)}
          </button>
        ))}
      </div>
    </div>
  );
}
