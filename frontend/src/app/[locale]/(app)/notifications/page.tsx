"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { CheckCheck, Loader2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, type Notification } from "@/lib/api";

export default function NotificationsPage() {
  const t = useTranslations("notifications");
  const locale = useLocale();
  const router = useRouter();
  const [items, setItems] = useState<Notification[] | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let stop = false;
    api
      .listNotifications({ limit: 50, unread: unreadOnly || undefined })
      .then((rows) => {
        if (!stop) setItems(rows);
      })
      .catch(() => {
        if (!stop) setItems([]);
      });
    return () => {
      stop = true;
    };
  }, [unreadOnly]);

  const unreadCount = (items ?? []).filter((n) => !n.read_at).length;

  async function click(n: Notification) {
    if (!n.read_at) {
      try {
        await api.markNotificationRead(n.id);
        setItems((cur) =>
          cur ? cur.map((x) => (x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x)) : cur,
        );
      } catch {
        /* ignore — navigation is more useful than blocking */
      }
    }
    if (n.link_url) router.push(`/${locale}${n.link_url}`);
  }

  async function markAll() {
    setBusy(true);
    try {
      await api.markAllNotificationsRead();
      setItems((cur) =>
        cur ? cur.map((x) => ({ ...x, read_at: x.read_at ?? new Date().toISOString() })) : cur,
      );
    } finally {
      setBusy(false);
    }
  }

  async function dismiss(n: Notification, e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await api.deleteNotification(n.id);
      setItems((cur) => (cur ? cur.filter((x) => x.id !== n.id) : cur));
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        {unreadCount > 0 && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={markAll}
            disabled={busy}
            className="gap-1.5"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCheck className="h-4 w-4" />}
            {t("markAllRead")}
          </Button>
        )}
      </div>

      <div className="inline-flex rounded-lg border bg-muted/40 p-0.5 text-sm">
        <button
          type="button"
          onClick={() => setUnreadOnly(false)}
          className={
            !unreadOnly
              ? "rounded-md bg-background px-3 py-1 font-medium shadow-sm"
              : "px-3 py-1 text-muted-foreground"
          }
        >
          {t("all")}
        </button>
        <button
          type="button"
          onClick={() => setUnreadOnly(true)}
          className={
            unreadOnly
              ? "rounded-md bg-background px-3 py-1 font-medium shadow-sm"
              : "px-3 py-1 text-muted-foreground"
          }
        >
          {t("unread")}
          {unreadCount > 0 ? ` (${unreadCount})` : ""}
        </button>
      </div>

      <Card className="overflow-hidden">
        {items === null ? (
          <div className="grid place-items-center py-16">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-sm text-muted-foreground">{t("empty")}</div>
        ) : (
          <ul className="divide-y">
            {items.map((n) => (
              <li
                key={n.id}
                onClick={() => click(n)}
                className={`group flex cursor-pointer items-start gap-3 px-4 py-3 transition-colors hover:bg-muted/40 ${
                  !n.read_at ? "bg-primary/5" : ""
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    {!n.read_at && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />}
                    <span className="truncate text-sm font-medium">{n.title}</span>
                  </div>
                  {n.body && <div className="mt-0.5 text-sm text-muted-foreground">{n.body}</div>}
                  <div className="mt-1 text-xs text-muted-foreground">
                    {new Date(n.created_at).toLocaleString(locale)}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={(e) => dismiss(n, e)}
                  aria-label={t("dismiss")}
                  className="invisible mt-0.5 rounded p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive group-hover:visible"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
