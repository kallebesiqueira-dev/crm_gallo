"use client";

import { use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Pencil, Sparkles, Trash2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useConfirm } from "@/components/confirm-dialog";
import { ActivityTimeline } from "@/components/activity-timeline";
import { AttachmentsPanel } from "@/components/attachments-panel";
import { CustomFieldsDisplay } from "@/components/custom-fields-input";
import { EntityTags } from "@/components/entity-tags";
import { NotesPanel } from "@/components/notes-panel";
import { PageSpinner } from "@/components/page-spinner";
import { AvatarUpload } from "@/components/avatar-upload";
import { useToast } from "@/components/toast-provider";
import {
  useCustomer,
  useCustomerDeals,
  useDeleteCustomer,
  useSummarizeCustomer,
} from "@/lib/use-customers";

function formatMoney(value: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
}

export default function CustomerDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("customers");
  const tCommon = useTranslations("common");
  const tTags = useTranslations("tags");
  const locale = useLocale();
  const router = useRouter();
  const confirm = useConfirm();
  const toast = useToast();

  const customerQuery = useCustomer(id);
  const customer = customerQuery.data;
  const deals = useCustomerDeals(id).data ?? [];
  const summarize = useSummarizeCustomer(id);
  const deleteCustomer = useDeleteCustomer();

  async function handleSummarize() {
    try {
      await summarize.mutateAsync();
      toast("Summary updated", "success");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
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
    try {
      await deleteCustomer.mutateAsync(customer.id);
      router.push(`/${locale}/customers`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    }
  }

  if (customerQuery.isError && !customer) {
    return <p className="text-sm text-destructive">{(customerQuery.error as Error).message}</p>;
  }
  if (!customer) return <PageSpinner />;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-4">
                <AvatarUpload
                  entityType="customer"
                  entityId={customer.id}
                  fallback={((customer.first_name[0] ?? "") + (customer.last_name[0] ?? "")).toUpperCase() || "?"}
                  size={64}
                />
                <div>
                  <CardTitle className="text-2xl">
                    {customer.first_name} {customer.last_name}
                  </CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">{customer.company ?? "—"}</p>
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
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
        {/* Linked deals */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">{t("deals")}</CardTitle>
              <Badge variant="secondary">{deals.length}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            {deals.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noDeals")}</p>
            ) : (
              <ul className="space-y-2">
                {deals.map((d) => (
                  <li key={d.id}>
                    <Link
                      href={`/${locale}/pipeline/${d.id}`}
                      className="flex items-center justify-between rounded-md p-2 hover:bg-muted/50 transition-colors"
                    >
                      <span className="truncate text-sm font-medium">{d.title}</span>
                      <span className="ml-3 shrink-0 text-xs text-muted-foreground">
                        {formatMoney(d.value, d.currency)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* AI summary */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">{t("aiSummary")}</CardTitle>
              <Button size="sm" onClick={handleSummarize} disabled={summarize.isPending}>
                <Sparkles className="h-4 w-4" />
                {summarize.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : t("summarize")}
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
      <div className="mt-1 break-words text-sm">{value || "—"}</div>
    </div>
  );
}
