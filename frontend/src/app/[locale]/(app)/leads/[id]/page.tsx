"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Pencil, Sparkles, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useConfirm } from "@/components/confirm-dialog";
import { ActivityTimeline } from "@/components/activity-timeline";
import { AttachmentsPanel } from "@/components/attachments-panel";
import { CustomFieldsDisplay } from "@/components/custom-fields-input";
import { EntityTags } from "@/components/entity-tags";
import { NotesPanel } from "@/components/notes-panel";
import { api, type Lead, type LeadStage } from "@/lib/api";
import { getToken } from "@/lib/auth";

const STAGES: LeadStage[] = [
  "new",
  "contacted",
  "qualified",
  "proposal_sent",
  "negotiation",
  "won",
  "lost",
];

export default function LeadDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("leads");
  const tStages = useTranslations("leads.stages");
  const tCommon = useTranslations("common");
  const tTags = useTranslations("tags");
  const locale = useLocale();
  const router = useRouter();
  const confirm = useConfirm();
  const [lead, setLead] = useState<Lead | null>(null);
  const [scoring, setScoring] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    if (!lead) return;
    const ok = await confirm({
      title: tCommon("confirmDelete"),
      tone: "danger",
      confirmLabel: tCommon("delete"),
    });
    if (!ok) return;
    const token = getToken();
    if (!token) return;
    try {
      await api.deleteLead(token, lead.id);
      router.push(`/${locale}/leads`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.getLead(token, id).then(setLead).catch((e) => setError(String(e)));
  }, [id]);

  async function changeStage(stage: LeadStage) {
    const token = getToken();
    if (!token || !lead) return;
    const updated = await api.updateLead(token, lead.id, { stage });
    setLead(updated);
  }

  async function runScore() {
    const token = getToken();
    if (!token || !lead) return;
    setScoring(true);
    setError(null);
    try {
      const scored = await api.scoreLead(token, lead.id);
      setLead(scored);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scoring failed");
    } finally {
      setScoring(false);
    }
  }

  // Only a LOAD failure (no lead yet) should replace the page. A scoring or
  // delete error must not wipe the detail view — it shows inline instead.
  if (error && !lead) return <p className="text-sm text-destructive">{error}</p>;
  if (!lead) return <p className="text-sm text-muted-foreground">…</p>;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle className="text-2xl">
                  {lead.first_name} {lead.last_name}
                </CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">{lead.company ?? "—"}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge>{tStages(lead.stage)}</Badge>
                <Button asChild size="sm">
                  <Link href={`/${locale}/leads/${lead.id}/edit`}>
                    <Pencil className="h-4 w-4" />
                    {tCommon("edit")}
                  </Link>
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  onClick={handleDelete}
                >
                  <Trash2 className="h-4 w-4" />
                  {tCommon("delete")}
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Email" value={lead.email} />
            <Field label="Phone" value={lead.phone} />
            <Field label="Industry" value={lead.industry} />
            <Field label="Country" value={lead.country} />
            <Field label="Company size" value={lead.company_size?.toString()} />
            <Field label="Budget" value={lead.budget?.toString()} />
            <Field label="Source" value={lead.source} />
            <Field
              label={t("created")}
              value={new Date(lead.created_at).toLocaleString(locale)}
            />
            {lead.notes && (
              <div className="sm:col-span-2">
                <div className="text-xs uppercase tracking-wider text-muted-foreground">
                  Notes
                </div>
                <p className="mt-1 whitespace-pre-wrap text-sm">{lead.notes}</p>
              </div>
            )}
            <div className="sm:col-span-2">
              <CustomFieldsDisplay entityType="lead" value={lead.custom_fields} />
            </div>
            <div className="sm:col-span-2">
              <div className="mb-1.5 text-xs uppercase tracking-wider text-muted-foreground">
                {tTags("title")}
              </div>
              <EntityTags entityType="lead" entityId={lead.id} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("stage")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {STAGES.map((s) => (
                <Button
                  key={s}
                  variant={s === lead.stage ? "default" : "outline"}
                  size="sm"
                  onClick={() => changeStage(s)}
                >
                  {tStages(s)}
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Per-user markdown notes panel — creating one also emits
            a `note_added` activity so the timeline below reflects it. */}
        <NotesPanel entityType="lead" entityId={lead.id} />

        {/* File attachments (S3-backed). Upload/download/delete all
            emit activities so the timeline reflects them. */}
        <AttachmentsPanel entityType="lead" entityId={lead.id} />

        {/* User-facing timeline — auto-emitted by lead.create /
            stage-change / score / note_added / file_attached etc. */}
        <ActivityTimeline entityType="lead" entityId={lead.id} />
      </div>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">{t("score")}</CardTitle>
              <Button size="sm" onClick={runScore} disabled={scoring}>
                <Sparkles className="h-4 w-4" />
                {scoring ? "…" : t("scoreNow")}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {error && (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
            )}
            {lead.ai_score != null ? (
              <>
                <div className="text-4xl font-semibold">{lead.ai_score}</div>
                <div className="text-sm text-muted-foreground">
                  Priority:{" "}
                  <span className="font-medium text-foreground">{lead.ai_priority ?? "—"}</span>
                </div>
                <div className="text-sm text-muted-foreground">
                  Conversion probability:{" "}
                  <span className="font-medium text-foreground">
                    {lead.ai_conversion_probability != null
                      ? `${(lead.ai_conversion_probability * 100).toFixed(0)}%`
                      : "—"}
                  </span>
                </div>
                {lead.ai_next_action && (
                  <div>
                    <div className="text-xs uppercase tracking-wider text-muted-foreground">
                      Next action
                    </div>
                    <p className="mt-1 text-sm">{lead.ai_next_action}</p>
                  </div>
                )}
                {lead.ai_risk_analysis && (
                  <div>
                    <div className="text-xs uppercase tracking-wider text-muted-foreground">
                      Risk analysis
                    </div>
                    <p className="mt-1 text-sm">{lead.ai_risk_analysis}</p>
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">{t("scoreEmpty")}</p>
            )}
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
      <div className="mt-1 text-sm">{value || "—"}</div>
    </div>
  );
}
