"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { useConfirm } from "@/components/confirm-dialog";
import {
  type AutomationAction,
  type AutomationRule,
  type AutomationTrigger,
  type DealStage,
} from "@/lib/api";
import {
  useAutomationRuns,
  useAutomations,
  useCreateAutomation,
  useDeleteAutomation,
  useUpdateAutomation,
} from "@/lib/use-automations";

const TRIGGERS: AutomationTrigger[] = [
  "lead_created",
  "deal_created",
  "deal_won",
  "deal_lost",
  "deal_stage_changed",
  "customer_created",
  "task_overdue",
  "user_invited",
  "lead_stale",
];
const ACTIONS: AutomationAction[] = ["create_task", "send_notification", "change_stage"];
const DEAL_STAGES: DealStage[] = ["new", "qualified", "proposal_sent", "negotiation", "won", "lost"];
const DEAL_TRIGGERS = new Set<AutomationTrigger>([
  "deal_created",
  "deal_won",
  "deal_lost",
  "deal_stage_changed",
]);

export default function AutomationsPage() {
  const t = useTranslations("automations");
  const tCommon = useTranslations("common");
  const tStages = useTranslations("leads.stages");
  const confirm = useConfirm();

  const automationsQuery = useAutomations();
  const rules = automationsQuery.data ?? [];
  const runs = useAutomationRuns().data ?? [];
  const createAutomation = useCreateAutomation();
  const updateAutomation = useUpdateAutomation();
  const deleteAutomation = useDeleteAutomation();
  const loading = automationsQuery.isLoading;
  const errored = [automationsQuery, createAutomation, updateAutomation, deleteAutomation].find(
    (m) => m.isError,
  );
  const error = errored ? (errored.error as Error).message : null;

  // Create form
  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState<AutomationTrigger>("lead_created");
  const [action, setAction] = useState<AutomationAction>("create_task");
  const [cfgTitle, setCfgTitle] = useState("");
  const [cfgBody, setCfgBody] = useState("");
  const [cfgToStage, setCfgToStage] = useState<DealStage>("qualified");
  const [cfgDueInDays, setCfgDueInDays] = useState("");
  const [cfgStaleDays, setCfgStaleDays] = useState("7");

  // change_stage only applies to deal triggers — if the user picks a lead
  // trigger while change_stage is selected, fall back to a safe action.
  useEffect(() => {
    if (action === "change_stage" && !DEAL_TRIGGERS.has(trigger)) {
      setAction("create_task");
    }
  }, [trigger, action]);

  function buildConfig(): Record<string, unknown> {
    const cfg: Record<string, unknown> = {};
    if (trigger === "lead_stale") {
      const d = Number(cfgStaleDays);
      if (Number.isFinite(d) && d >= 0) cfg.stale_days = Math.trunc(d);
    }
    if (action === "create_task") {
      if (cfgTitle.trim()) cfg.title = cfgTitle.trim();
      const due = Number(cfgDueInDays);
      if (cfgDueInDays !== "" && Number.isFinite(due) && due >= 0) cfg.due_in_days = Math.trunc(due);
    } else if (action === "send_notification") {
      if (cfgTitle.trim()) cfg.title = cfgTitle.trim();
      if (cfgBody.trim()) cfg.body = cfgBody.trim();
    } else if (action === "change_stage") {
      cfg.to_stage = cfgToStage;
    }
    return cfg;
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await createAutomation.mutateAsync({
        name: name.trim(),
        trigger,
        action,
        action_config: buildConfig(),
      });
      setName("");
      setCfgTitle("");
      setCfgBody("");
      setCfgDueInDays("");
    } catch {
      /* surfaced via error */
    }
  }

  function handleToggle(rule: AutomationRule) {
    updateAutomation.mutate({ id: rule.id, payload: { enabled: !rule.enabled } });
  }

  async function handleDelete(rule: AutomationRule) {
    const ok = await confirm({
      title: t("confirmDeleteTitle"),
      description: t("confirmDeleteBody", { name: rule.name }),
      confirmLabel: tCommon("delete"),
    });
    if (!ok) return;
    deleteAutomation.mutate(rule.id);
  }

  const ruleBusy = (id: string) =>
    (updateAutomation.isPending && updateAutomation.variables?.id === id) ||
    (deleteAutomation.isPending && deleteAutomation.variables === id);

  const availableActions = useMemo(
    () => (DEAL_TRIGGERS.has(trigger) ? ACTIONS : ACTIONS.filter((a) => a !== "change_stage")),
    [trigger],
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Create rule */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">{t("newRule")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCreate} className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-1 sm:col-span-2 lg:col-span-1">
              <Label htmlFor="a-name">{t("name")}</Label>
              <Input id="a-name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="space-y-1">
              <Label htmlFor="a-trigger">{t("trigger")}</Label>
              <Select
                id="a-trigger"
                value={trigger}
                onChange={(e) => setTrigger(e.target.value as AutomationTrigger)}
              >
                {TRIGGERS.map((tr) => (
                  <option key={tr} value={tr}>
                    {t(`triggers.${tr}`)}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="a-action">{t("action")}</Label>
              <Select
                id="a-action"
                value={action}
                onChange={(e) => setAction(e.target.value as AutomationAction)}
              >
                {availableActions.map((a) => (
                  <option key={a} value={a}>
                    {t(`actions.${a}`)}
                  </option>
                ))}
              </Select>
            </div>

            {trigger === "lead_stale" && (
              <div className="space-y-1">
                <Label htmlFor="a-stale">{t("staleDays")}</Label>
                <Input
                  id="a-stale"
                  type="number"
                  min="0"
                  value={cfgStaleDays}
                  onChange={(e) => setCfgStaleDays(e.target.value)}
                />
              </div>
            )}

            {(action === "create_task" || action === "send_notification") && (
              <div className="space-y-1">
                <Label htmlFor="a-title">{t("cfgTitle")}</Label>
                <Input
                  id="a-title"
                  value={cfgTitle}
                  onChange={(e) => setCfgTitle(e.target.value)}
                  placeholder={t("cfgTitlePlaceholder")}
                />
              </div>
            )}
            {action === "create_task" && (
              <div className="space-y-1">
                <Label htmlFor="a-due">{t("dueInDays")}</Label>
                <Input
                  id="a-due"
                  type="number"
                  min="0"
                  value={cfgDueInDays}
                  onChange={(e) => setCfgDueInDays(e.target.value)}
                  placeholder="3"
                />
              </div>
            )}
            {action === "send_notification" && (
              <div className="space-y-1">
                <Label htmlFor="a-body">{t("cfgBody")}</Label>
                <Input id="a-body" value={cfgBody} onChange={(e) => setCfgBody(e.target.value)} />
              </div>
            )}
            {action === "change_stage" && (
              <div className="space-y-1">
                <Label htmlFor="a-stage">{t("toStage")}</Label>
                <Select
                  id="a-stage"
                  value={cfgToStage}
                  onChange={(e) => setCfgToStage(e.target.value as DealStage)}
                >
                  {DEAL_STAGES.map((s) => (
                    <option key={s} value={s}>
                      {tStages(s)}
                    </option>
                  ))}
                </Select>
              </div>
            )}

            <div className="flex items-end">
              <Button type="submit" disabled={createAutomation.isPending || !name.trim()}>
                {t("addRule")}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Rules list */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">{t("rules")}</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="grid place-items-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : rules.length === 0 ? (
            <p className="py-8 text-center text-xs text-muted-foreground">{t("noRules")}</p>
          ) : (
            <ul className="space-y-3">
              {rules.map((rule) => (
                <li key={rule.id} className="rounded-md border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="truncate font-medium">{rule.name}</span>
                      {!rule.enabled && <Badge variant="secondary">{t("disabled")}</Badge>}
                    </div>
                    <div className="flex shrink-0 items-center gap-2 text-sm">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => handleToggle(rule)}
                        disabled={ruleBusy(rule.id)}
                      >
                        {rule.enabled ? t("disable") : t("enable")}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(rule)}
                        disabled={ruleBusy(rule.id)}
                        aria-label={tCommon("delete")}
                      >
                        {tCommon("delete")}
                      </Button>
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Badge variant="secondary">{t(`triggers.${rule.trigger}`)}</Badge>
                    <span aria-hidden>→</span>
                    <Badge variant="secondary">{t(`actions.${rule.action}`)}</Badge>
                    <span className="ml-auto">
                      {t("ranTimes", { count: rule.run_count })}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Run log */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">{t("runLog")}</CardTitle>
        </CardHeader>
        <CardContent>
          {runs.length === 0 ? (
            <p className="py-6 text-center text-xs text-muted-foreground">{t("noRuns")}</p>
          ) : (
            <ul className="divide-y text-sm">
              {runs.map((run) => (
                <li key={run.id} className="flex items-center justify-between gap-3 py-2">
                  <span className="flex min-w-0 items-center gap-2">
                    <Badge
                      variant={
                        run.status === "success"
                          ? "success"
                          : run.status === "failed"
                            ? "danger"
                            : "secondary"
                      }
                    >
                      {t(`status.${run.status}`)}
                    </Badge>
                    <span className="truncate text-muted-foreground">{run.detail ?? "—"}</span>
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {new Date(run.created_at).toLocaleString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
