"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Paperclip, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";

const CATEGORIES = ["technical", "bug", "feature", "question", "other"] as const;

export function SupportDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useTranslations("support");
  const [category, setCategory] = useState<string>("technical");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [screenshot, setScreenshot] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  if (!open) return null;

  function reset() {
    setCategory("technical");
    setTitle("");
    setDescription("");
    setScreenshot(null);
    setError(null);
    setSent(false);
  }
  function close() {
    reset();
    onClose();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !description.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.reportIssue({
        category,
        title: title.trim(),
        description: description.trim(),
        page_url: window.location.href,
        user_agent: navigator.userAgent,
        screenshot,
      });
      setSent(true);
      setTimeout(close, 1300);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[100] grid place-items-center bg-black/50 p-4"
      onClick={close}
      role="presentation"
    >
      <div
        className="w-full max-w-md rounded-xl border bg-background p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold">{t("title")}</h2>
          <button
            type="button"
            onClick={close}
            aria-label={t("cancel")}
            className="text-muted-foreground transition hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {sent ? (
          <p className="py-8 text-center text-sm font-medium text-emerald-600">{t("sent")}</p>
        ) : (
          <form onSubmit={submit} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="sup-cat">{t("category")} *</Label>
              <Select
                id="sup-cat"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {t(`categories.${c}`)}
                  </option>
                ))}
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="sup-title">{t("titleField")} *</Label>
              <Input
                id="sup-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                maxLength={150}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="sup-desc">{t("description")} *</Label>
              <Textarea
                id="sup-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                required
                className="min-h-[110px]"
              />
            </div>

            <label className="flex cursor-pointer items-center gap-2 rounded-md border border-dashed border-input px-3 py-2.5 text-sm text-muted-foreground transition hover:border-primary/50">
              <Paperclip className="h-4 w-4 shrink-0" />
              <span className="flex-1 truncate">{screenshot ? screenshot.name : t("attach")}</span>
              <input
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => setScreenshot(e.target.files?.[0] ?? null)}
              />
            </label>

            <p className="text-xs text-muted-foreground">{t("autoInfo")}</p>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="ghost" onClick={close}>
                {t("cancel")}
              </Button>
              <Button type="submit" disabled={busy || !title.trim() || !description.trim()}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : t("submit")}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
