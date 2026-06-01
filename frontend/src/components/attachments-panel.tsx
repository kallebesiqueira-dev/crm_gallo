"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Download,
  File as FileIcon,
  FileImage,
  FileText,
  Loader2,
  Paperclip,
  Trash2,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type FileAttachment } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Per-entity file attachments. Mounted on Lead/Customer/Deal detail
 * alongside Notes + Activity timeline.
 *
 * Upload: standard `<input type="file">` triggered by a button.
 * Download: GET presigned URL, then redirect the browser there so
 * bytes stream straight from S3.
 * Delete: confirms, then sets the row's `deleted_at` AND hard-
 * deletes the blob server-side.
 *
 * Backend enforces a 25 MB cap (HTTP 413 if exceeded). We surface
 * the message inline; pre-validating size client-side would be a
 * nice-to-have but the server is the source of truth.
 */
interface Props {
  entityType: "lead" | "customer" | "deal";
  entityId: string;
}

const MIME_ICONS: { match: (m: string) => boolean; Icon: React.ComponentType<{ className?: string }> }[] = [
  { match: (m) => m.startsWith("image/"), Icon: FileImage },
  { match: (m) => m === "application/pdf" || m.startsWith("text/"), Icon: FileText },
];

export function AttachmentsPanel({ entityType, entityId }: Props) {
  const t = useTranslations("attachments");
  const [items, setItems] = useState<FileAttachment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function refresh() {
    try {
      setItems(await api.listAttachments(entityType, entityId));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityType, entityId]);

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await api.uploadAttachment(entityType, entityId, file);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      // Reset so re-uploading the same file fires `change` again.
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function download(att: FileAttachment) {
    try {
      const { url } = await api.attachmentDownloadUrl(att.id);
      // `_self` so the browser navigates (and triggers
      // Content-Disposition: attachment from the presigned URL).
      // An anchor tag with `download` attr would force-save even
      // when the file is inline-renderable (PDF, image).
      window.location.href = url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    }
  }

  async function remove(att: FileAttachment) {
    if (!confirm(t("confirmDelete", { name: att.filename }))) return;
    setPendingDelete(att.id);
    setError(null);
    try {
      await api.deleteAttachment(att.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setPendingDelete(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Paperclip className="h-4 w-4" />
          {t("title")}
          {items && (
            <span className="text-xs font-normal text-muted-foreground">
              ({items.length})
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex items-center gap-2">
          <input
            ref={fileInput}
            type="file"
            className="hidden"
            onChange={onPick}
          />
          <Button
            type="button"
            size="sm"
            disabled={uploading}
            onClick={() => fileInput.current?.click()}
          >
            {uploading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Upload className="h-3.5 w-3.5" />
            )}
            {uploading ? t("uploading") : t("upload")}
          </Button>
          <span className="text-xs text-muted-foreground">{t("sizeHint")}</span>
        </div>

        {items === null ? (
          <div className="grid place-items-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {items.map((att) => {
              const Icon =
                MIME_ICONS.find((m) => m.match(att.content_type))?.Icon ?? FileIcon;
              return (
                <li
                  key={att.id}
                  className="flex items-center gap-3 px-3 py-2 text-sm"
                >
                  <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{att.filename}</div>
                    <div className="text-xs text-muted-foreground">
                      {formatSize(att.size_bytes)} · {att.uploader_name || att.uploader_email || t("unknownUploader")} · {formatWhen(att.created_at)}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => download(att)}
                    aria-label={t("download")}
                    className="rounded-md border border-transparent p-1.5 text-muted-foreground transition-colors hover:border-foreground/30 hover:bg-muted hover:text-foreground"
                  >
                    <Download className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(att)}
                    disabled={pendingDelete === att.id}
                    aria-label={t("delete")}
                    className={cn(
                      "rounded-md border border-transparent p-1.5 text-muted-foreground transition-colors",
                      "hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive",
                    )}
                  >
                    {pendingDelete === att.id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="h-3.5 w-3.5" />
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
