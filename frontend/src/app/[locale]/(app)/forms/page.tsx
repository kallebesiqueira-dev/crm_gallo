"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Check, Code2, Copy, Inbox, Loader2, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useConfirm } from "@/components/confirm-dialog";
import { API_URL, type WebForm } from "@/lib/api";
import { useCreateForm, useDeleteForm, useForms, useUpdateForm } from "@/lib/use-forms";

function embedSnippet(token: string): string {
  const action = `${API_URL}/api/public/forms/${token}/submit`;
  return [
    `<form action="${action}" method="POST">`,
    `  <input type="text" name="first_name" placeholder="First name" required />`,
    `  <input type="text" name="last_name" placeholder="Last name" />`,
    `  <input type="email" name="email" placeholder="Email" />`,
    `  <input type="tel" name="phone" placeholder="Phone" />`,
    `  <input type="text" name="company" placeholder="Company" />`,
    `  <textarea name="message" placeholder="Message"></textarea>`,
    `  <!-- anti-spam honeypot: keep hidden, leave empty -->`,
    `  <input type="text" name="website" tabindex="-1" autocomplete="off"`,
    `         aria-hidden="true" style="position:absolute;left:-9999px" />`,
    `  <button type="submit">Send</button>`,
    `</form>`,
  ].join("\n");
}

export default function FormsPage() {
  const t = useTranslations("forms");
  const tCommon = useTranslations("common");
  const confirm = useConfirm();

  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [showSnippet, setShowSnippet] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [defaultSource, setDefaultSource] = useState("");
  const [redirectUrl, setRedirectUrl] = useState("");

  const formsQuery = useForms();
  const forms = formsQuery.data ?? [];
  const createForm = useCreateForm();
  const updateForm = useUpdateForm();
  const deleteForm = useDeleteForm();

  const loading = formsQuery.isLoading;
  const errored = [formsQuery, createForm, updateForm, deleteForm].find((m) => m.isError);
  const error = errored ? (errored.error as Error).message : null;
  const formBusy = (id: string) =>
    (updateForm.isPending && updateForm.variables?.id === id) ||
    (deleteForm.isPending && deleteForm.variables === id);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await createForm.mutateAsync({
        name: name.trim(),
        default_source: defaultSource.trim() || null,
        redirect_url: redirectUrl.trim() || null,
      });
      setName("");
      setDefaultSource("");
      setRedirectUrl("");
    } catch {
      /* surfaced via error */
    }
  }

  function toggleActive(form: WebForm) {
    updateForm.mutate({ id: form.id, payload: { active: !form.active } });
  }

  async function handleDelete(form: WebForm) {
    const ok = await confirm({
      title: t("confirmDeleteTitle"),
      description: t("confirmDeleteBody", { name: form.name }),
      confirmLabel: tCommon("delete"),
    });
    if (!ok) return;
    deleteForm.mutate(form.id);
  }

  async function copySnippet(form: WebForm) {
    try {
      await navigator.clipboard.writeText(embedSnippet(form.token));
      setCopiedId(form.id);
      setTimeout(() => setCopiedId((c) => (c === form.id ? null : c)), 2000);
    } catch {
      /* clipboard blocked — the snippet is still visible to copy by hand */
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <Card className="p-4">
        <form onSubmit={handleCreate} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="form-name">{t("name")}</Label>
            <Input
              id="form-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("namePlaceholder")}
              required
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="form-source">{t("defaultSource")}</Label>
            <Input
              id="form-source"
              value={defaultSource}
              onChange={(e) => setDefaultSource(e.target.value)}
              placeholder={t("defaultSourcePlaceholder")}
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="form-redirect">{t("redirectUrl")}</Label>
            <Input
              id="form-redirect"
              type="url"
              value={redirectUrl}
              onChange={(e) => setRedirectUrl(e.target.value)}
              placeholder="https://example.com/thank-you"
            />
          </div>
          <div className="sm:col-span-2">
            <Button type="submit" disabled={createForm.isPending || !name.trim()}>
              {createForm.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              {t("create")}
            </Button>
          </div>
        </form>
      </Card>

      {loading ? (
        <div className="flex justify-center p-10 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : forms.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-10 text-center text-sm text-muted-foreground">
          <Inbox className="h-6 w-6" />
          {t("empty")}
        </Card>
      ) : (
        <div className="space-y-3">
          {forms.map((form) => {
            const busy = formBusy(form.id);
            const open = showSnippet === form.id;
            return (
              <Card key={form.id} className="p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium">{form.name}</span>
                      <Badge variant={form.active ? "success" : "secondary"}>
                        {form.active ? t("active") : t("paused")}
                      </Badge>
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {t("submissions", { count: form.submission_count })}
                      {form.default_source ? ` · ${form.default_source}` : ""}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setShowSnippet(open ? null : form.id)}
                    >
                      <Code2 className="h-4 w-4" />
                      {t("embed")}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => toggleActive(form)}
                      disabled={busy}
                    >
                      {busy ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : form.active ? (
                        t("pause")
                      ) : (
                        t("resume")
                      )}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(form)}
                      disabled={busy}
                      aria-label={tCommon("delete")}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>

                {open && (
                  <div className="mt-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="text-xs text-muted-foreground">{t("embedHelp")}</p>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => copySnippet(form)}
                      >
                        {copiedId === form.id ? (
                          <Check className="h-4 w-4 text-emerald-600" />
                        ) : (
                          <Copy className="h-4 w-4" />
                        )}
                        {copiedId === form.id ? t("copied") : t("copy")}
                      </Button>
                    </div>
                    <pre className="overflow-x-auto rounded-md border bg-muted/40 p-3 text-xs">
                      <code>{embedSnippet(form.token)}</code>
                    </pre>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
