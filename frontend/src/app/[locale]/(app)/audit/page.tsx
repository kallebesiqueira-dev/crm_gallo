"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { ChevronLeft, ChevronRight, Loader2, ScrollText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type AuditEntry } from "@/lib/api";

/**
 * Admin / manager audit log browser.
 *
 * The backend enforces the role check (admin or manager only); the
 * page itself isn't hidden from the sidebar for other roles in v1
 * — a sales_agent landing here gets a 403 from the API and we
 * surface a friendly notice. Could add nav gating later.
 *
 * Filters:
 *   - `action` substring (ILIKE) — admins typically know the prefix
 *     ("lead.", "user.", "billing.")
 *   - `entity_type` exact — "lead" | "customer" | "user" | etc
 *   - `since` / `until` ISO date pickers
 *
 * Pagination: simple limit/offset with prev/next buttons. Cursor
 * paging is a P2 improvement; the audit ledger isn't write-heavy
 * enough at our current scale for offset drift to matter.
 */
const PAGE_SIZE = 50;

export default function AuditPage() {
  const t = useTranslations("audit");
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [offset, setOffset] = useState(0);

  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");

  async function load(newOffset = offset) {
    setBusy(true);
    setError(null);
    try {
      const data = await api.listAudit({
        action: action || undefined,
        entity_type: entityType || undefined,
        since: since ? new Date(since).toISOString() : undefined,
        until: until ? new Date(until + "T23:59:59").toISOString() : undefined,
        limit: PAGE_SIZE,
        offset: newOffset,
      });
      setEntries(data);
      setOffset(newOffset);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function applyFilters(e: React.FormEvent) {
    e.preventDefault();
    load(0);
  }

  return (
    <div className="space-y-4">
      {/* Page header outside the card — same pattern as the other screens. */}
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10">
          <ScrollText className="h-5 w-5 text-primary" />
        </div>
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
      </div>

      <Card>
        <CardContent className="space-y-4 pt-6">
          <form onSubmit={applyFilters} className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div className="space-y-1.5">
              <Label htmlFor="action">{t("filterAction")}</Label>
              <Input
                id="action"
                placeholder="lead.create"
                value={action}
                onChange={(e) => setAction(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="entity">{t("filterEntity")}</Label>
              <Input
                id="entity"
                placeholder="lead | user"
                value={entityType}
                onChange={(e) => setEntityType(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="since">{t("filterSince")}</Label>
              <Input
                id="since"
                type="date"
                value={since}
                onChange={(e) => setSince(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="until">{t("filterUntil")}</Label>
              <Input
                id="until"
                type="date"
                value={until}
                onChange={(e) => setUntil(e.target.value)}
              />
            </div>
            <div className="flex items-end">
              <Button type="submit" disabled={busy} className="w-full">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : t("apply")}
              </Button>
            </div>
          </form>

          {error && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error.toLowerCase().includes("insufficient role")
                ? t("forbidden")
                : error}
            </div>
          )}

          {entries === null ? (
            <div className="grid place-items-center py-10">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : entries.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted-foreground">
              {t("noResults")}
            </p>
          ) : (
            <div className="overflow-x-auto">
              {/* Graduated column reveal (same pattern as the list tables):
                  phone = when + action (actor folded under the action),
                  sm adds the actor column, md the entity, lg the metadata. */}
              <table className="w-full text-sm">
                <thead className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-3">{t("colWhen")}</th>
                    <th className="hidden py-2 pr-3 sm:table-cell">{t("colActor")}</th>
                    <th className="py-2 pr-3">{t("colAction")}</th>
                    <th className="hidden py-2 pr-3 md:table-cell">{t("colEntity")}</th>
                    <th className="hidden py-2 pr-3 lg:table-cell">{t("colMetadata")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {entries.map((e) => (
                    <tr key={e.id} className="align-top">
                      <td className="whitespace-nowrap py-2 pr-3 text-xs text-muted-foreground">
                        {formatWhen(e.created_at)}
                      </td>
                      <td className="hidden py-2 pr-3 sm:table-cell">
                        {e.actor_name ? (
                          <div className="min-w-0">
                            <div className="max-w-[16rem] truncate font-medium">{e.actor_name}</div>
                            <div className="max-w-[16rem] truncate text-xs text-muted-foreground">
                              {e.actor_email}
                            </div>
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            {t("system")}
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-3">
                        <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                          {e.action}
                        </code>
                        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground sm:hidden">
                          {e.actor_name ?? t("system")}
                        </span>
                      </td>
                      <td className="hidden py-2 pr-3 text-xs md:table-cell">
                        <span className="text-muted-foreground">{e.entity_type}</span>
                        {e.entity_id && (
                          <span className="block font-mono text-[10px] text-muted-foreground/70">
                            {e.entity_id}
                          </span>
                        )}
                      </td>
                      <td className="hidden py-2 pr-3 lg:table-cell">
                        {e.metadata_json ? (
                          <code className="block max-w-xs overflow-hidden text-ellipsis whitespace-nowrap rounded bg-muted/50 px-1.5 py-0.5 font-mono text-[10px]">
                            {e.metadata_json}
                          </code>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>
              {t("showingRange", {
                from: offset + 1,
                to: offset + (entries?.length ?? 0),
              })}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0 || busy}
                onClick={() => load(Math.max(0, offset - PAGE_SIZE))}
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                {t("prev")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={busy || (entries?.length ?? 0) < PAGE_SIZE}
                onClick={() => load(offset + PAGE_SIZE)}
              >
                {t("next")}
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
