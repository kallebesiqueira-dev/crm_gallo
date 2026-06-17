"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { CalendarClock, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useConfirm } from "@/components/confirm-dialog";
import { ActivityTimeline } from "@/components/activity-timeline";
import { AttachmentsPanel } from "@/components/attachments-panel";
import { NotesPanel } from "@/components/notes-panel";
import { PageSpinner } from "@/components/page-spinner";
import { useToast } from "@/components/toast-provider";
import { type DealStage, type NextActionType } from "@/lib/api";
import { useDeal, useDeleteDeal, useSetNextAction, useUpdateDeal } from "@/lib/use-deals";
import { ActionIcon } from "@/lib/action-icons";

const STAGES: DealStage[] = [
  "new",
  "qualified",
  "proposal_sent",
  "negotiation",
  "won",
  "lost",
];

const CURRENCY_SYMBOL: Record<string, string> = { EUR: "€", CHF: "CHF ", USD: "$", GBP: "£" };

const NEXT_ACTION_TYPES = [
  "call",
  "whatsapp",
  "email",
  "proposal",
  "meeting",
  "follow_up",
  "contract",
  "chase",
  "other",
] as const;


function formatMoney(value: number, currency: string) {
  const sym = CURRENCY_SYMBOL[currency] ?? currency + " ";
  return `${sym}${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function DealDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("pipeline");
  const tActions = useTranslations("pipeline.actions");
  const tStages = useTranslations("leads.stages");
  const tCommon = useTranslations("common");
  const tNotes = useTranslations("notes");
  const locale = useLocale();
  const router = useRouter();
  const confirm = useConfirm();
  const toast = useToast();

  const dealQuery = useDeal(id);
  const deal = dealQuery.data;
  const updateDeal = useUpdateDeal(id);
  const setNextAction = useSetNextAction(id);
  const deleteDeal = useDeleteDeal();

  // Next-action form state, seeded from the deal once it loads.
  const [naType, setNaType] = useState<NextActionType | "">("");
  const [naAt, setNaAt] = useState("");

  useEffect(() => {
    if (!deal) return;
    setNaType((deal.next_action_type as NextActionType | null) ?? "");
    setNaAt(deal.next_action_at ? deal.next_action_at.slice(0, 16) : "");
    // Seed only when the loaded deal id changes — don't clobber edits on refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deal?.id]);

  async function changeStage(stage: DealStage) {
    try {
      await updateDeal.mutateAsync({ stage });
      toast(t("stageUpdated"), "success");
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  }

  async function saveNextAction(e: React.FormEvent) {
    e.preventDefault();
    try {
      await setNextAction.mutateAsync({
        next_action_type: (naType as NextActionType) || null,
        next_action_at: naAt ? new Date(naAt).toISOString() : null,
      });
      toast(t("followUpSaved"), "success");
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  }

  async function handleDelete() {
    if (!deal) return;
    const ok = await confirm({
      title: tCommon("confirmDelete"),
      tone: "danger",
      confirmLabel: tCommon("delete"),
    });
    if (!ok) return;
    try {
      await deleteDeal.mutateAsync(deal.id);
      router.push(`/${locale}/pipeline`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  if (dealQuery.isError && !deal) {
    return <p className="text-sm text-destructive">{(dealQuery.error as Error).message}</p>;
  }
  if (!deal) return <PageSpinner />;

  const isOverdue =
    deal.next_action_at != null && new Date(deal.next_action_at) < new Date();
  const isToday =
    deal.next_action_at != null &&
    new Date(deal.next_action_at).toDateString() === new Date().toDateString();

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="min-w-0 space-y-6 lg:col-span-2">
        {/* Hero card — actions wrap under the title on narrow screens
            instead of squeezing it (they were shrink-0 beside it). */}
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <CardTitle className="break-words text-2xl">{deal.title}</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  {formatMoney(deal.value, deal.currency)}
                  {" · "}
                  {deal.probability}%
                </p>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <Badge>{tStages(deal.stage)}</Badge>
                <Button asChild size="sm">
                  <Link href={`/${locale}/pipeline/${deal.id}/edit`}>
                    <Pencil className="h-4 w-4" />
                    {tCommon("edit")}
                  </Link>
                </Button>
                <Button type="button" variant="destructive" size="sm" onClick={handleDelete}>
                  <Trash2 className="h-4 w-4" />
                  {tCommon("delete")}
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label={t("value")} value={formatMoney(deal.value, deal.currency)} />
            <Field label={t("probability")} value={`${deal.probability}%`} />
            <Field
              label={t("expectedClose")}
              value={
                deal.expected_close_date
                  ? new Date(deal.expected_close_date).toLocaleDateString(locale)
                  : null
              }
            />
            <Field label={t("created")} value={new Date(deal.created_at).toLocaleDateString(locale)} />
            {deal.next_action_type && (
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground">
                  {t("nextAction")}
                </div>
                <div
                  className={
                    isOverdue
                      ? "mt-1 text-sm font-medium text-red-600"
                      : isToday
                      ? "mt-1 text-sm font-medium text-amber-600"
                      : "mt-1 text-sm"
                  }
                >
                  <ActionIcon
                    type={deal.next_action_type}
                    className="mr-1 inline h-4 w-4 align-text-bottom"
                  />
                  {tActions(deal.next_action_type)}
                  {deal.next_action_at && (
                    <span className="ml-2 text-xs text-muted-foreground">
                      {new Date(deal.next_action_at).toLocaleString(locale, {
                        day: "numeric",
                        month: "short",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  )}
                </div>
              </div>
            )}
            {deal.notes && (
              <div className="sm:col-span-2">
                <div className="text-xs uppercase tracking-wider text-muted-foreground">
                  {tNotes("title")}
                </div>
                <p className="mt-1 whitespace-pre-wrap break-words text-sm">{deal.notes}</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Stage selector */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("stage")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {STAGES.map((s) => (
                <Button
                  key={s}
                  variant={s === deal.stage ? "default" : "outline"}
                  size="sm"
                  disabled={updateDeal.isPending}
                  onClick={() => changeStage(s)}
                >
                  {tStages(s)}
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>

        <NotesPanel entityType="deal" entityId={deal.id} />
        <AttachmentsPanel entityType="deal" entityId={deal.id} />
        <ActivityTimeline entityType="deal" entityId={deal.id} />
      </div>

      {/* Sidebar: next action scheduler */}
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <CalendarClock className="h-4 w-4 text-primary" />
              <CardTitle className="text-base">{t("nextAction")}</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {!deal.next_action_at && !deal.next_action_type && (
              <p className="mb-4 text-sm text-muted-foreground">{t("noNextAction")}</p>
            )}
            <form onSubmit={saveNextAction} className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="na-type">{t("actionType")}</Label>
                <Select
                  id="na-type"
                  value={naType}
                  onChange={(e) => setNaType(e.target.value as NextActionType | "")}
                >
                  <option value="">—</option>
                  {NEXT_ACTION_TYPES.map((k) => (
                    <option key={k} value={k}>
                      {tActions(k)}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="na-at">{t("scheduledFor")}</Label>
                <Input
                  id="na-at"
                  type="datetime-local"
                  value={naAt}
                  onChange={(e) => setNaAt(e.target.value)}
                />
              </div>
              <Button type="submit" size="sm" disabled={setNextAction.isPending} className="w-full">
                {setNextAction.isPending ? tCommon("loading") : t("saveFollowUp")}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 break-words text-sm">{value || "—"}</div>
    </div>
  );
}
