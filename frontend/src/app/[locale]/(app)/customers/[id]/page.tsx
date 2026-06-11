"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Pencil, Sparkles, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useConfirm } from "@/components/confirm-dialog";
import { ActivityTimeline } from "@/components/activity-timeline";
import { AttachmentsPanel } from "@/components/attachments-panel";
import { CustomFieldsDisplay } from "@/components/custom-fields-input";
import { EntityTags } from "@/components/entity-tags";
import { NotesPanel } from "@/components/notes-panel";
import { api, type Customer } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function CustomerDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("customers");
  const tCommon = useTranslations("common");
  const tTags = useTranslations("tags");
  const locale = useLocale();
  const router = useRouter();
  const confirm = useConfirm();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.getCustomer(token, id).then(setCustomer).catch((e) => setError(String(e)));
  }, [id]);

  async function summarize() {
    const token = getToken();
    if (!token || !customer) return;
    setBusy(true);
    try {
      const updated = await api.summarizeCustomer(token, customer.id);
      setCustomer(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!customer) return;
    const ok = await confirm({
      title: tCommon("confirmDelete"),
      tone: "danger",
      confirmLabel: tCommon("delete"),
    });
    if (!ok) return;
    const token = getToken();
    if (!token) return;
    try {
      await api.deleteCustomer(token, customer.id);
      router.push(`/${locale}/customers`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!customer) return <p className="text-sm text-muted-foreground">…</p>;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle className="text-2xl">
                  {customer.first_name} {customer.last_name}
                </CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">{customer.company ?? "—"}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button asChild size="sm">
                  <Link href={`/${locale}/customers/${customer.id}/edit`}>
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
            <Field label="Email" value={customer.email} />
            <Field label="Phone" value={customer.phone} />
            <Field label="Industry" value={customer.industry} />
            <Field label="Country" value={customer.country} />
            <Field label="Website" value={customer.website} />
            <Field
              label={t("created")}
              value={new Date(customer.created_at).toLocaleString(locale)}
            />
            {customer.address && (
              <div className="sm:col-span-2">
                <div className="text-xs uppercase tracking-wider text-muted-foreground">
                  Address
                </div>
                <p className="mt-1 text-sm">{customer.address}</p>
              </div>
            )}
            {customer.notes && (
              <div className="sm:col-span-2">
                <div className="text-xs uppercase tracking-wider text-muted-foreground">Notes</div>
                <p className="mt-1 whitespace-pre-wrap text-sm">{customer.notes}</p>
              </div>
            )}
            <div className="sm:col-span-2">
              <CustomFieldsDisplay entityType="customer" value={customer.custom_fields} />
            </div>
            <div className="sm:col-span-2">
              <div className="mb-1.5 text-xs uppercase tracking-wider text-muted-foreground">
                {tTags("title")}
              </div>
              <EntityTags entityType="customer" entityId={customer.id} />
            </div>
          </CardContent>
        </Card>

        <NotesPanel entityType="customer" entityId={customer.id} />
        <AttachmentsPanel entityType="customer" entityId={customer.id} />
        <ActivityTimeline entityType="customer" entityId={customer.id} />
      </div>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">{t("aiSummary")}</CardTitle>
              <Button size="sm" onClick={summarize} disabled={busy}>
                <Sparkles className="h-4 w-4" />
                {busy ? "…" : t("summarize")}
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {customer.ai_summary ? (
              <p className="whitespace-pre-wrap text-sm">{customer.ai_summary}</p>
            ) : (
              <p className="text-sm text-muted-foreground">{t("noSummary")}</p>
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
