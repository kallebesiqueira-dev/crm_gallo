"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useConfirm } from "@/components/confirm-dialog";
import { ActivityTimeline } from "@/components/activity-timeline";
import { CustomFieldsDisplay } from "@/components/custom-fields-input";
import { EntityTags } from "@/components/entity-tags";
import { NotesPanel } from "@/components/notes-panel";
import { api, type CompanyRollup } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function CompanyDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("companies");
  const tCommon = useTranslations("common");
  const tTags = useTranslations("tags");
  const locale = useLocale();
  const router = useRouter();
  const confirm = useConfirm();
  const [data, setData] = useState<CompanyRollup | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.getCompanyRollup(token, id).then(setData).catch((e) => setError(String(e)));
  }, [id]);

  async function handleDelete() {
    if (!data) return;
    const ok = await confirm({
      title: tCommon("confirmDelete"),
      tone: "danger",
      confirmLabel: tCommon("delete"),
    });
    if (!ok) return;
    const token = getToken();
    if (!token) return;
    try {
      await api.deleteCompany(token, data.company.id);
      router.push(`/${locale}/companies`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">…</p>;

  const { company, customers, leads, deals } = data;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle className="text-2xl">{company.name}</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">{company.industry ?? "—"}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button asChild size="sm">
                  <Link href={`/${locale}/companies/${company.id}/edit`}>
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
            <Field label={t("website")} value={company.website} />
            <Field label={t("email")} value={company.email} />
            <Field label={t("phone")} value={company.phone} />
            <Field label={t("country")} value={company.country} />
            <Field label={t("size")} value={company.size != null ? String(company.size) : null} />
            <Field
              label={t("created")}
              value={new Date(company.created_at).toLocaleString(locale)}
            />
            {company.address && (
              <div className="sm:col-span-2">
                <div className="text-xs uppercase tracking-wider text-muted-foreground">
                  {t("address")}
                </div>
                <p className="mt-1 text-sm">{company.address}</p>
              </div>
            )}
            {company.notes && (
              <div className="sm:col-span-2">
                <div className="text-xs uppercase tracking-wider text-muted-foreground">
                  {t("notes")}
                </div>
                <p className="mt-1 whitespace-pre-wrap text-sm">{company.notes}</p>
              </div>
            )}
            <div className="sm:col-span-2">
              <CustomFieldsDisplay entityType="company" value={company.custom_fields} />
            </div>
            <div className="sm:col-span-2">
              <div className="mb-1.5 text-xs uppercase tracking-wider text-muted-foreground">
                {tTags("title")}
              </div>
              <EntityTags entityType="company" entityId={company.id} />
            </div>
          </CardContent>
        </Card>

        <NotesPanel entityType="company" entityId={company.id} />
        <ActivityTimeline entityType="company" entityId={company.id} />
      </div>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("customers")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {customers.length === 0 && leads.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noContacts")}</p>
            ) : (
              <>
                {customers.map((c) => (
                  <Link
                    key={c.id}
                    href={`/${locale}/customers/${c.id}`}
                    className="block text-sm text-primary hover:underline"
                  >
                    {c.first_name} {c.last_name}
                  </Link>
                ))}
                {leads.map((l) => (
                  <Link
                    key={l.id}
                    href={`/${locale}/leads/${l.id}`}
                    className="block text-sm text-muted-foreground hover:underline"
                  >
                    {l.first_name} {l.last_name} · {t("leads")}
                  </Link>
                ))}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("deals")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {deals.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noDeals")}</p>
            ) : (
              deals.map((d) => (
                <Link
                  key={d.id}
                  href={`/${locale}/pipeline`}
                  className="flex items-center justify-between text-sm hover:underline"
                >
                  <span className="text-primary">{d.title}</span>
                  <span className="text-muted-foreground">
                    {d.value.toLocaleString(locale, { style: "currency", currency: d.currency })}
                  </span>
                </Link>
              ))
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
