"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import {
  Check,
  Download,
  FileSignature,
  FileText,
  Loader2,
  Pencil,
  RotateCcw,
  Send,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useConfirm } from "@/components/confirm-dialog";
import { SignaturePanel } from "@/components/signature-panel";
import { api, type DocumentTemplate, type FileAttachment, type Quote } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { STATUS_VARIANT } from "../status";

export default function QuoteDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("quotes");
  const tCommon = useTranslations("common");
  const tTpl = useTranslations("documentTemplates");
  const locale = useLocale();
  const router = useRouter();
  const confirm = useConfirm();

  const [quote, setQuote] = useState<Quote | null>(null);
  const [docs, setDocs] = useState<FileAttachment[]>([]);
  const [templates, setTemplates] = useState<DocumentTemplate[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const money = (n: number) => (quote ? `${quote.currency} ${n.toFixed(2)}` : n.toFixed(2));

  const loadDocs = useCallback(async () => {
    try {
      setDocs(await api.listAttachments("quote", id));
    } catch {
      /* non-fatal */
    }
  }, [id]);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.getQuote(token, id).then(setQuote).catch((e) => setError(String(e)));
    loadDocs();
    api.listDocumentTemplates(token).then(setTemplates).catch(() => {});
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [id, loadDocs]);

  async function act(fn: () => Promise<Quote>) {
    setBusy(true);
    setError(null);
    try {
      setQuote(await fn());
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
      await api.deleteQuote(token, id);
      router.push(`/${locale}/quotes`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  async function handleResend() {
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const fresh = await api.resendQuote(token, id);
      router.push(`/${locale}/quotes/${fresh.id}/edit`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
      setBusy(false);
    }
  }

  async function handleCreateContract() {
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const contract = await api.createContractFromQuote(
        token,
        id,
        selectedTemplate || undefined,
      );
      router.push(`/${locale}/contracts/${contract.id}`);
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
      await api.generateQuotePdf(token, id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
      setGenerating(false);
      return;
    }
    // The worker renders async (~15s) and attaches the PDF. Poll the
    // attachments list until a new one shows up, then stop.
    let tries = 0;
    const poll = async () => {
      tries += 1;
      await loadDocs();
      const current = await api.listAttachments("quote", id);
      if (current.length > before || tries >= 10) {
        setDocs(current);
        setGenerating(false);
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

  if (error && !quote) return <p className="text-sm text-destructive">{error}</p>;
  if (!quote) return <p className="text-sm text-muted-foreground">…</p>;

  const isDraft = quote.status === "draft";
  const isSent = quote.status === "sent";
  const isAccepted = quote.status === "accepted";
  const canResend = quote.status !== "draft";

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{quote.title}</h1>
            <Badge variant={STATUS_VARIANT[quote.status]}>{t(`statuses.${quote.status}`)}</Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {quote.number} · {t("version", { n: quote.version })}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isDraft && (
            <>
              <Button asChild size="sm" variant="outline">
                <Link href={`/${locale}/quotes/${quote.id}/edit`}>
                  <Pencil className="h-4 w-4" />
                  {tCommon("edit")}
                </Link>
              </Button>
              <Button
                size="sm"
                disabled={busy}
                onClick={() => act(() => api.sendQuote(getToken()!, id))}
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
            <>
              <Button
                size="sm"
                disabled={busy}
                onClick={() => act(() => api.acceptQuote(getToken()!, id))}
              >
                <Check className="h-4 w-4" />
                {t("accept")}
              </Button>
              <Button
                size="sm"
                variant="destructive"
                disabled={busy}
                onClick={() => act(() => api.declineQuote(getToken()!, id))}
              >
                <X className="h-4 w-4" />
                {t("decline")}
              </Button>
            </>
          )}
          {isAccepted && (
            <>
              {templates.length > 0 && (
                <select
                  aria-label={tTpl("chooseTemplate")}
                  value={selectedTemplate}
                  onChange={(e) => setSelectedTemplate(e.target.value)}
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                >
                  <option value="">{tTpl("noTemplate")}</option>
                  {templates.map((tpl) => (
                    <option key={tpl.id} value={tpl.id}>
                      {tpl.name}
                    </option>
                  ))}
                </select>
              )}
              <Button size="sm" disabled={busy} onClick={handleCreateContract}>
                <FileSignature className="h-4 w-4" />
                {t("createContract")}
              </Button>
            </>
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

      {quote.superseded_by && (
        <Card>
          <CardContent className="py-3 text-sm text-muted-foreground">
            {t("supersededBy")}{" "}
            <Link
              href={`/${locale}/quotes/${quote.superseded_by}`}
              className="font-medium text-primary hover:underline"
            >
              →
            </Link>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2 text-left font-medium">{t("lineDescription")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("quantity")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("unitPrice")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("lineTotal")}</th>
              </tr>
            </thead>
            <tbody>
              {quote.line_items.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-muted-foreground">
                    {t("noLines")}
                  </td>
                </tr>
              ) : (
                quote.line_items.map((li) => (
                  <tr key={li.id} className="border-b last:border-0">
                    <td className="px-4 py-2">{li.description}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{li.quantity}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(li.unit_price)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(li.line_total)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          <div className="ml-auto max-w-xs space-y-1 p-4 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t("subtotal")}</span>
              <span className="tabular-nums">{money(quote.subtotal)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">
                {t("tax")} ({quote.tax_rate}%)
              </span>
              <span className="tabular-nums">{money(quote.tax_amount)}</span>
            </div>
            <div className="flex justify-between border-t pt-1 font-semibold">
              <span>{t("total")}</span>
              <span className="tabular-nums">{money(quote.total)}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {quote.notes && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("notes")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-wrap text-sm">{quote.notes}</p>
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

      <SignaturePanel documentId={quote.id} documentType="quote" documentStatus={quote.status} />
    </div>
  );
}
