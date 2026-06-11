"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import {
  Ban,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  Pencil,
  PenLine,
  RotateCcw,
  Send,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useConfirm } from "@/components/confirm-dialog";
import { SignaturePanel } from "@/components/signature-panel";
import { api, type Contract, type DocumentTemplate, type FileAttachment } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { STATUS_VARIANT } from "../status";

export default function ContractDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("contracts");
  const tCommon = useTranslations("common");
  const tTpl = useTranslations("documentTemplates");
  const locale = useLocale();
  const router = useRouter();
  const confirm = useConfirm();

  const [contract, setContract] = useState<Contract | null>(null);
  const [docs, setDocs] = useState<FileAttachment[]>([]);
  const [templates, setTemplates] = useState<DocumentTemplate[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [applying, setApplying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const money = (n: number) => (contract ? `${contract.currency} ${n.toFixed(2)}` : n.toFixed(2));

  const loadDocs = useCallback(async () => {
    try {
      setDocs(await api.listAttachments("contract", id));
    } catch {
      /* non-fatal */
    }
  }, [id]);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.getContract(token, id).then(setContract).catch((e) => setError(String(e)));
    loadDocs();
    api.listDocumentTemplates(token).then(setTemplates).catch(() => {});
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [id, loadDocs]);

  async function applyTemplate() {
    if (!selectedTemplate) return;
    const token = getToken();
    if (!token) return;
    setApplying(true);
    setError(null);
    try {
      setContract(await api.applyContractTemplate(token, id, selectedTemplate));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setApplying(false);
    }
  }

  async function act(fn: () => Promise<Contract>) {
    setBusy(true);
    setError(null);
    try {
      setContract(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    const ok = await confirm({
      title: t("confirmDelete"),
      tone: "danger",
      confirmLabel: tCommon("delete"),
    });
    if (!ok) return;
    const token = getToken();
    if (!token) return;
    try {
      await api.deleteContract(token, id);
      router.push(`/${locale}/contracts`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  async function handleTerminate() {
    const ok = await confirm({
      title: t("confirmTerminate"),
      tone: "danger",
      confirmLabel: t("terminate"),
    });
    if (!ok) return;
    await act(() => api.terminateContract(getToken()!, id));
  }

  async function handleResend() {
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const fresh = await api.resendContract(token, id);
      router.push(`/${locale}/contracts/${fresh.id}/edit`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
      setBusy(false);
    }
  }

  async function generatePdf() {
    const token = getToken();
    if (!token) return;
    setGenerating(true);
    setError(null);
    const before = docs.length;
    try {
      await api.generateContractPdf(token, id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
      setGenerating(false);
      return;
    }
    // Poll the attachments list until the rendered PDF shows up. The worker
    // render + R2 upload usually lands in well under 30s, but we allow a 60s
    // window (20 × 3s) so a cold worker or a busy queue doesn't make the
    // spinner give up before the PDF appears.
    let tries = 0;
    const poll = async () => {
      tries += 1;
      const current = await api.listAttachments("contract", id);
      if (current.length > before) {
        setDocs(current);
        setGenerating(false);
        return;
      }
      if (tries >= 20) {
        setDocs(current);
        setGenerating(false);
        setError(t("pdfPending"));
        return;
      }
      pollTimer.current = setTimeout(poll, 3000);
    };
    pollTimer.current = setTimeout(poll, 3000);
  }

  async function download(doc: FileAttachment) {
    try {
      const { url } = await api.attachmentDownloadUrl(doc.id);
      window.location.href = url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  if (error && !contract) return <p className="text-sm text-destructive">{error}</p>;
  if (!contract) return <p className="text-sm text-muted-foreground">…</p>;

  const isDraft = contract.status === "draft";
  const isSent = contract.status === "sent";
  const isSigned = contract.status === "signed";
  const isActive = contract.status === "active";
  const canResend = contract.status !== "draft";

  const fmtDate = (d: string | null) =>
    d ? new Date(d).toLocaleDateString(locale) : "—";

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{contract.title}</h1>
            <Badge variant={STATUS_VARIANT[contract.status]}>
              {t(`statuses.${contract.status}`)}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {contract.number} · {t("version", { n: contract.version })}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isDraft && (
            <>
              <Button asChild size="sm" variant="outline">
                <Link href={`/${locale}/contracts/${contract.id}/edit`}>
                  <Pencil className="h-4 w-4" />
                  {tCommon("edit")}
                </Link>
              </Button>
              <Button
                size="sm"
                disabled={busy}
                onClick={() => act(() => api.sendContract(getToken()!, id))}
              >
                <Send className="h-4 w-4" />
                {t("send")}
              </Button>
              <Button size="sm" variant="destructive" disabled={busy} onClick={handleDelete}>
                <Trash2 className="h-4 w-4" />
                {tCommon("delete")}
              </Button>
            </>
          )}
          {isSent && (
            <Button
              size="sm"
              disabled={busy}
              onClick={() => act(() => api.signContract(getToken()!, id))}
            >
              <PenLine className="h-4 w-4" />
              {t("sign")}
            </Button>
          )}
          {isSigned && (
            <Button
              size="sm"
              disabled={busy}
              onClick={() => act(() => api.activateContract(getToken()!, id))}
            >
              <CheckCircle2 className="h-4 w-4" />
              {t("activate")}
            </Button>
          )}
          {(isSigned || isActive) && (
            <Button size="sm" variant="destructive" disabled={busy} onClick={handleTerminate}>
              <Ban className="h-4 w-4" />
              {t("terminate")}
            </Button>
          )}
          {canResend && (
            <Button size="sm" variant="outline" disabled={busy} onClick={handleResend}>
              <RotateCcw className="h-4 w-4" />
              {t("resend")}
            </Button>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {contract.superseded_by && (
        <Card>
          <CardContent className="py-3 text-sm text-muted-foreground">
            {t("supersededBy")}{" "}
            <Link
              href={`/${locale}/contracts/${contract.superseded_by}`}
              className="font-medium text-primary hover:underline"
            >
              →
            </Link>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="grid gap-x-8 gap-y-3 p-6 text-sm sm:grid-cols-2">
          <Field label={t("value")} value={money(contract.value)} />
          <Field label={t("currency")} value={contract.currency} />
          <Field label={t("effectiveDate")} value={fmtDate(contract.effective_date)} />
          <Field label={t("endDate")} value={fmtDate(contract.end_date)} />
          <Field
            label={t("autoRenew")}
            value={
              contract.auto_renew
                ? contract.renewal_term_months
                  ? t("renewEvery", { n: contract.renewal_term_months })
                  : t("yes")
                : t("no")
            }
          />
          {contract.quote_id && (
            <Field
              label={t("sourceQuote")}
              value={
                <Link
                  href={`/${locale}/quotes/${contract.quote_id}`}
                  className="font-medium text-primary hover:underline"
                >
                  {t("viewQuote")}
                </Link>
              }
            />
          )}
        </CardContent>
      </Card>

      {isDraft && templates.length > 0 && (
        <Card>
          <CardContent className="flex flex-wrap items-end gap-2 p-4">
            <div className="min-w-[200px] flex-1 space-y-1.5">
              <label
                htmlFor="apply-template"
                className="text-xs uppercase tracking-wider text-muted-foreground"
              >
                {tTpl("applyToContract")}
              </label>
              <select
                id="apply-template"
                value={selectedTemplate}
                onChange={(e) => setSelectedTemplate(e.target.value)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="">{tTpl("chooseTemplate")}</option>
                {templates.map((tpl) => (
                  <option key={tpl.id} value={tpl.id}>
                    {tpl.name}
                    {tpl.is_default ? ` (${tTpl("default")})` : ""}
                  </option>
                ))}
              </select>
            </div>
            <Button onClick={applyTemplate} disabled={applying || !selectedTemplate}>
              {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
              {tTpl("apply")}
            </Button>
          </CardContent>
        </Card>
      )}

      {contract.body && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("termsSection")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-wrap text-sm">{contract.body}</p>
          </CardContent>
        </Card>
      )}

      {contract.notes && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("notes")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-wrap text-sm">{contract.notes}</p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">{t("documents")}</CardTitle>
            <Button size="sm" variant="outline" disabled={generating} onClick={generatePdf}>
              {generating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <FileText className="h-4 w-4" />
              )}
              {generating ? t("generating") : t("generatePdf")}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {docs.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("noDocuments")}</p>
          ) : (
            <ul className="divide-y rounded-md border">
              {docs.map((doc) => (
                <li key={doc.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate">{doc.filename}</span>
                  <button
                    type="button"
                    onClick={() => download(doc)}
                    aria-label={t("generatePdf")}
                    className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                  >
                    <Download className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <SignaturePanel
        documentId={contract.id}
        documentType="contract"
        documentStatus={contract.status}
      />
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </div>
  );
}
