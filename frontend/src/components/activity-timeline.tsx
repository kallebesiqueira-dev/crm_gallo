"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Activity as ActivityIcon,
  ArrowRight,
  CheckCircle2,
  FileEdit,
  Mail,
  MessageSquare,
  Paperclip,
  Phone,
  PlusCircle,
  Sparkles,
  Trash2,
  Users,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type ActivityEntry } from "@/lib/api";

/**
 * User-facing timeline rendered on lead / customer / deal detail
 * pages. Reads `GET /api/activities?entity_type=&entity_id=`.
 *
 * Renders each row with:
 *   - icon mapped from the activity `type` slug
 *   - localised primary line (built from `type` + `metadata_json`
 *     for structured types like stage_change, or `content` for free-
 *     form types like note_added)
 *   - actor name + relative timestamp
 *
 * Unknown types degrade to a generic "activity" label + icon. New
 * types in the backend `ActivityType` enum land here without code
 * changes; only adding a translation + icon is needed for the
 * polished look.
 */

interface Props {
  entityType: "lead" | "customer" | "deal";
  entityId: string;
}

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  created: PlusCircle,
  updated: FileEdit,
  deleted: Trash2,
  restored: Sparkles,
  stage_change: ArrowRight,
  ai_scored: Sparkles,
  note_added: MessageSquare,
  file_attached: Paperclip,
  file_removed: Paperclip,
  call: Phone,
  meeting: Users,
  email_sent: Mail,
  email_received: Mail,
  task_completed: CheckCircle2,
  imported: PlusCircle,
  system: ActivityIcon,
};

export function ActivityTimeline({ entityType, entityId }: Props) {
  const t = useTranslations("activity");
  const [items, setItems] = useState<ActivityEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listActivities(entityType, entityId, { limit: 50 })
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Load failed");
      });
    return () => {
      cancelled = true;
    };
  }, [entityType, entityId]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ActivityIcon className="h-4 w-4" />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {error && <p className="text-sm text-destructive">{error}</p>}
        {items === null ? (
          <p className="text-sm text-muted-foreground">{t("loading")}</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ol className="space-y-3">
            {items.map((it) => (
              <TimelineRow key={it.id} entry={it} t={t} />
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

function TimelineRow({
  entry,
  t,
}: {
  entry: ActivityEntry;
  t: ReturnType<typeof useTranslations>;
}) {
  const Icon = ICONS[entry.type] ?? ActivityIcon;
  const label = labelFor(entry, t);
  const actor = entry.actor_name || entry.actor_email || t("systemActor");
  return (
    <li className="flex gap-3">
      <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full border bg-muted/50">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm">{label}</div>
        <div className="text-xs text-muted-foreground">
          {actor} · {formatWhen(entry.created_at)}
        </div>
      </div>
    </li>
  );
}

/**
 * Build the human label for one row. Structured types
 * (stage_change, ai_scored) parse `metadata_json` so the line reads
 * "Stage: new → qualified" rather than a generic "updated". For
 * unknown types fall back to the type slug verbatim (signals "we
 * should add a translation" without breaking the page).
 */
function labelFor(
  entry: ActivityEntry,
  t: ReturnType<typeof useTranslations>,
): string {
  const meta = parseMeta(entry.metadata_json);
  switch (entry.type) {
    case "created":
      return t("typeCreated");
    case "updated":
      return t("typeUpdated");
    case "deleted":
      return t("typeDeleted");
    case "restored":
      return t("typeRestored");
    case "stage_change":
      return t("typeStageChange", {
        from: String(meta?.from ?? "?"),
        to: String(meta?.to ?? "?"),
      });
    case "ai_scored":
      return t("typeAiScored", {
        score: String(meta?.score ?? "?"),
        priority: String(meta?.priority ?? ""),
      });
    case "note_added":
      return entry.content || t("typeNoteAdded");
    case "file_attached":
      return t("typeFileAttached", { name: entry.content || "file" });
    case "file_removed":
      return t("typeFileRemoved", { name: entry.content || "file" });
    case "call":
      return entry.content || t("typeCall");
    case "meeting":
      return entry.content || t("typeMeeting");
    case "email_sent":
      return entry.content || t("typeEmailSent");
    case "email_received":
      return entry.content || t("typeEmailReceived");
    case "task_completed":
      return entry.content || t("typeTaskCompleted");
    case "imported":
      return t("typeImported");
    case "system":
      return entry.content || t("typeSystem");
    default:
      return entry.content || entry.type;
  }
}

function parseMeta(raw: string | null): Record<string, unknown> | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
