"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { CopyCheck, Download, FileUp, Loader2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  api,
  ApiError,
  type ImportEntityType,
  type ImportJob,
  type ImportMode,
  type ImportStatus,
} from "@/lib/api";

const STATUS_VARIANT: Record<ImportStatus, "secondary" | "warning" | "success" | "danger"> = {
  pending: "secondary",
  processing: "warning",
  completed: "success",
  failed: "danger",
};

function isTerminal(status: ImportStatus): boolean {
  return status === "completed" || status === "failed";
}

export default function ImportsPage() {
  const t = useTranslations("imports");
  const tNav = useTranslations("nav");
  const locale = useLocale();

  const [entityType, setEntityType] = useState<ImportEntityType>("lead");
  const [mode, setMode] = useState<ImportMode>("create");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const rows = await api.listImports();
      setJobs(rows);
    } catch {
      /* keep last-known list on a transient error */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll while any job is still pending/processing — the worker runs
  // out-of-band, so the list only converges on a terminal state via
  // polling. Stop the timer once everything has settled.
  useEffect(() => {
    const anyInFlight = jobs.some((j) => !isTerminal(j.status));
    if (!anyInFlight) return;
    const id = setInterval(refresh, 2000);
    return () => clearInterval(id);
  }, [jobs, refresh]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createImport(entityType, mode, file);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || t("uploadFailed"));
      } else {
        setError(t("uploadFailed"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function downloadTemplate() {
    try {
      const tpl = await api.importTemplate(entityType);
      const csv = tpl.headers.join(",") + "\r\n";
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${entityType}-import-template.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(t("templateFailed"));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        {/* Dedup lives here since it left the nav: import is where duplicates enter. */}
        <Button asChild size="sm" variant="outline" className="gap-1.5">
          <Link href={`/${locale}/duplicates`}>
            <CopyCheck className="h-4 w-4" />
            <span>{tNav("duplicates")}</span>
          </Link>
        </Button>
      </div>

      <Card className="p-6">
        <h2 className="text-lg font-medium">{t("startTitle")}</h2>
        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-sm font-medium">{t("entityType")}</span>
              <Select
                value={entityType}
                onChange={(e) => setEntityType(e.target.value as ImportEntityType)}
              >
                <option value="lead">{t("entityLead")}</option>
                <option value="customer">{t("entityCustomer")}</option>
              </Select>
            </label>

            <label className="space-y-1.5">
              <span className="text-sm font-medium">{t("mode")}</span>
              <Select
                value={mode}
                onChange={(e) => setMode(e.target.value as ImportMode)}
              >
                <option value="create">{t("modeCreate")}</option>
                <option value="upsert">{t("modeUpsert")}</option>
              </Select>
            </label>
          </div>

          <p className="text-xs text-muted-foreground">
            {mode === "create" ? t("modeCreateHint") : t("modeUpsertHint")}
          </p>

          <label className="block space-y-1.5">
            <span className="text-sm font-medium">{t("file")}</span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:text-sm file:font-medium file:text-primary-foreground hover:file:bg-primary/90"
            />
            <span className="text-xs text-muted-foreground">{t("fileHint")}</span>
          </label>

          {error && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={!file || submitting}>
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              {t("startButton")}
            </Button>
            <Button type="button" variant="outline" onClick={downloadTemplate}>
              <Download className="h-4 w-4" />
              {t("downloadTemplate")}
            </Button>
          </div>
        </form>
      </Card>

      <Card className="overflow-hidden">
        <div className="flex items-center gap-2 border-b px-6 py-4">
          <FileUp className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-lg font-medium">{t("recentTitle")}</h2>
        </div>
        {jobs.length === 0 ? (
          <div className="p-10 text-center text-sm text-muted-foreground">{t("empty")}</div>
        ) : (
          <div className="overflow-x-auto">
          <table className="w-full min-w-[44rem] text-sm">
            <thead className="bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">{t("colFile")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("colEntity")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("colStatus")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("colResult")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("colCreated")}</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id} className="border-t align-top hover:bg-muted/30">
                  <td className="px-4 py-3">
                    <div className="font-medium">{job.filename}</div>
                    {job.error_message && (
                      <div className="text-xs text-destructive">{job.error_message}</div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {job.entity_type === "lead" ? t("entityLead") : t("entityCustomer")}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={STATUS_VARIANT[job.status]}>{t(`status.${job.status}`)}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    {isTerminal(job.status) && job.status !== "failed" ? (
                      <span className="text-muted-foreground">
                        {t("resultSummary", {
                          created: job.created_count,
                          updated: job.updated_count,
                          skipped: job.skipped_count,
                          errors: job.error_count,
                        })}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(job.created_at).toLocaleString(locale)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </Card>

      <p className="text-xs text-muted-foreground">{t("pollNote")}</p>
    </div>
  );
}
