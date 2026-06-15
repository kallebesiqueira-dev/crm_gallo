"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import {
  DndContext,
  DragOverlay,
  MouseSensor,
  TouchSensor,
  closestCorners,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useDraggable } from "@dnd-kit/core";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useConfirm } from "@/components/confirm-dialog";
import { api, ApiError, type Deal, type DealStage } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";
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

function formatMoney(value: number, currency: string) {
  const symbol = CURRENCY_SYMBOL[currency] ?? "";
  return `${symbol}${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export default function PipelinePage() {
  const t = useTranslations("pipeline");
  const tStages = useTranslations("leads.stages");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const confirm = useConfirm();
  const [deals, setDeals] = useState<Deal[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete(deal: Deal) {
    const ok = await confirm({
      title: tCommon("confirmDelete"),
      tone: "danger",
      confirmLabel: tCommon("delete"),
    });
    if (!ok) return;
    const token = getToken();
    if (!token) return;
    setError(null);
    try {
      await api.deleteDeal(token, deal.id);
      setDeals((prev) => prev.filter((d) => d.id !== deal.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  // Mouse drags after 6px; touch drags after a 220ms long-press (so normal
  // page scroll still works on phones — a bare PointerSensor loses the
  // gesture to scrolling on iOS and the kanban can't be dragged at all).
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 220, tolerance: 8 } }),
  );

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.listDeals(token).then(setDeals).catch(() => setDeals([]));
  }, []);

  const byStage = useMemo(() => {
    const groups: Record<DealStage, Deal[]> = {
      new: [],
      qualified: [],
      proposal_sent: [],
      negotiation: [],
      won: [],
      lost: [],
    };
    for (const d of deals) groups[d.stage].push(d);
    for (const stage of STAGES) {
      groups[stage].sort((a, b) => a.sort_index - b.sort_index);
    }
    return groups;
  }, [deals]);

  const activeDeal = deals.find((d) => d.id === activeId) ?? null;

  function onDragStart(e: DragStartEvent) {
    setActiveId(String(e.active.id));
  }

  async function onDragEnd(e: DragEndEvent) {
    setActiveId(null);
    const { active, over } = e;
    if (!over) return;
    const dealId = String(active.id);
    const overId = String(over.id);
    // over.id may be a stage (when dropped on column) or a deal id (when dropped on another card).
    let targetStage: DealStage;
    if ((STAGES as readonly string[]).includes(overId)) {
      targetStage = overId as DealStage;
    } else {
      const overDeal = deals.find((d) => d.id === overId);
      if (!overDeal) return;
      targetStage = overDeal.stage;
    }
    const moving = deals.find((d) => d.id === dealId);
    if (!moving || moving.stage === targetStage) return;

    const targetMax = Math.max(0, ...byStage[targetStage].map((d) => d.sort_index));
    const newSortIndex = targetMax + 1;

    setDeals((prev) =>
      prev.map((d) =>
        d.id === dealId ? { ...d, stage: targetStage, sort_index: newSortIndex } : d,
      ),
    );

    const token = getToken();
    if (!token) return;
    try {
      const updated = await api.moveDeal(token, dealId, targetStage, newSortIndex, moving.version);
      setDeals((prev) => prev.map((d) => (d.id === dealId ? updated : d)));
    } catch (e) {
      if (e instanceof ApiError && e.status === 412) {
        setError(tCommon("versionConflict"));
      }
      // revert (and resync version) on any failure
      const refreshed = await api.listDeals(token);
      setDeals(refreshed);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <Button asChild>
          <Link href={`/${locale}/pipeline/new`}>
            <Plus className="h-4 w-4" />
            {t("new")}
          </Link>
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
      >
        <div className="grid gap-3 overflow-x-auto pb-4 md:grid-cols-3 xl:grid-cols-6">
          {STAGES.map((stage) => (
            <Column
              key={stage}
              stage={stage}
              label={tStages(stage)}
              deals={byStage[stage]}
              onDelete={handleDelete}
              deleteLabel={tCommon("delete")}
            />
          ))}
        </div>
        <DragOverlay>
          {activeDeal ? (
            <div className="rotate-1">
              <DealCard deal={activeDeal} dragging />
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}

function Column({
  stage,
  label,
  deals,
  onDelete,
  deleteLabel,
}: {
  stage: DealStage;
  label: string;
  deals: Deal[];
  onDelete?: (deal: Deal) => void;
  deleteLabel?: string;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: stage });
  const total = deals.reduce((acc, d) => acc + d.value, 0);

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex min-h-[300px] flex-col rounded-xl border bg-card p-3 transition-colors",
        isOver && "border-primary bg-primary/5",
      )}
    >
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold">{label}</div>
          <div className="text-xs text-muted-foreground">
            {deals.length} · {formatMoney(total, deals[0]?.currency ?? "EUR")}
          </div>
        </div>
      </div>
      <div className="space-y-2">
        {deals.map((d) => (
          <DealCard key={d.id} deal={d} onDelete={onDelete} deleteLabel={deleteLabel} />
        ))}
        {deals.length === 0 && (
          <div className="rounded-md border border-dashed py-6 text-center text-xs text-muted-foreground">
            ·
          </div>
        )}
      </div>
    </div>
  );
}

function DealCard({
  deal,
  dragging,
  onDelete,
  deleteLabel,
}: {
  deal: Deal;
  dragging?: boolean;
  onDelete?: (deal: Deal) => void;
  deleteLabel?: string;
}) {
  const locale = useLocale();
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: deal.id,
  });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;

  return (
    <Card
      ref={setNodeRef}
      style={style}
      className={cn(
        "relative p-3",
        (dragging || isDragging) && "opacity-60 shadow-lg",
      )}
    >
      {/* Drag handle covers the whole card except the delete button.
          touch-manipulation keeps taps/scroll responsive while letting the
          TouchSensor's long-press take over the gesture for dragging. */}
      <div
        {...listeners}
        {...attributes}
        className="cursor-grab touch-manipulation active:cursor-grabbing"
      >
        <div className="pr-6 text-sm font-medium">
          <a
            href={`/${locale}/pipeline/${deal.id}`}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
            className="hover:underline"
          >
            {deal.title}
          </a>
        </div>
        <div className="mt-1 flex items-center justify-between text-xs">
          <span className="font-mono text-muted-foreground">
            {formatMoney(deal.value, deal.currency)}
          </span>
          <Badge variant="outline" className="text-[10px]">
            {deal.probability}%
          </Badge>
        </div>
        {deal.expected_close_date && (
          <div className="mt-1 text-[10px] uppercase tracking-wider text-muted-foreground">
            {new Date(deal.expected_close_date).toLocaleDateString()}
          </div>
        )}
        {deal.next_action_at ? (
          <div className={cn(
            "mt-1.5 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px]",
            new Date(deal.next_action_at) < new Date()
              ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
              : new Date(deal.next_action_at).toDateString() === new Date().toDateString()
              ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
              : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
          )}>
            <ActionIcon type={deal.next_action_type} className="h-3 w-3" />
            <span>{new Date(deal.next_action_at).toLocaleDateString()}</span>
          </div>
        ) : (
          <div className="mt-1.5 text-[10px] italic text-muted-foreground/40">
            {t("noFollowUp")}
          </div>
        )}
      </div>
      {onDelete && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDelete(deal);
          }}
          aria-label={deleteLabel ?? "delete"}
          className="absolute right-2 top-2 text-muted-foreground hover:text-destructive"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </Card>
  );
}
