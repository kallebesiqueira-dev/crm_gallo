"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import {
  Bell,
  CheckCheck,
  Loader2,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, type Notification } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Header bell — unread badge + dropdown of recent notifications.
 *
 * Polls `/api/notifications/counts` every 60s for the badge (cheap
 * COUNT against the partial unread index); fetches the full list
 * only when the dropdown opens.
 *
 * Click on a notification: marks read + navigates to `link_url`
 * (prefixed with the current locale so router stays consistent).
 * "Mark all read" zeroes the badge in one round-trip.
 *
 * Polling cadence is intentional — the productised version would
 * push via SSE/WebSocket, but a 60s GET is the simplest thing that
 * works and keeps the smoke story trivial.
 */
const POLL_INTERVAL_MS = 60_000;

export function NotificationsBell() {
  const t = useTranslations("notifications");
  const router = useRouter();
  const locale = useLocale();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<Notification[] | null>(null);
  const [busy, setBusy] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Poll the count. Pauses while tab is hidden so we don't burn
  // requests on background tabs.
  useEffect(() => {
    let stopped = false;
    async function tick() {
      if (stopped || document.hidden) return;
      try {
        const { unread: n } = await api.notificationCounts();
        if (!stopped) setUnread(n);
      } catch {
        /* swallow — bell is best-effort, don't yell at the user */
      }
    }
    tick();
    const id = setInterval(tick, POLL_INTERVAL_MS);
    const onVisible = () => {
      if (!document.hidden) tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  // Close on outside click.
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (!dropdownRef.current) return;
      if (!dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", onClick);
      return () => document.removeEventListener("mousedown", onClick);
    }
  }, [open]);

  async function openDropdown() {
    setOpen(true);
    if (items === null) {
      try {
        setItems(await api.listNotifications({ limit: 20 }));
      } catch {
        setItems([]);
      }
    }
  }

  async function click(n: Notification) {
    if (!n.read_at) {
      try {
        await api.markNotificationRead(n.id);
        setItems((cur) =>
          cur ? cur.map((x) => (x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x)) : cur,
        );
        setUnread((u) => Math.max(0, u - 1));
      } catch {
        /* ignore — navigating anyway is more useful than blocking */
      }
    }
    setOpen(false);
    if (n.link_url) {
      // `link_url` is locale-less; prefix the active locale.
      router.push(`/${locale}${n.link_url}`);
    }
  }

  async function markAll() {
    setBusy(true);
    try {
      await api.markAllNotificationsRead();
      setItems((cur) =>
        cur ? cur.map((x) => ({ ...x, read_at: x.read_at ?? new Date().toISOString() })) : cur,
      );
      setUnread(0);
    } finally {
      setBusy(false);
    }
  }

  async function dismiss(n: Notification, e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await api.deleteNotification(n.id);
      setItems((cur) => (cur ? cur.filter((x) => x.id !== n.id) : cur));
      if (!n.read_at) setUnread((u) => Math.max(0, u - 1));
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => (open ? setOpen(false) : openDropdown())}
        aria-label={t("bell")}
        className="relative inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span
            className={cn(
              "absolute -right-0.5 -top-0.5 grid min-w-[18px] place-items-center rounded-full bg-destructive px-1 text-[10px] font-medium leading-tight text-destructive-foreground",
            )}
          >
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-md border bg-popover text-popover-foreground shadow-md sm:w-96">
          <div className="flex items-center justify-between border-b px-3 py-2">
            <div className="text-sm font-semibold">{t("title")}</div>
            {unread > 0 && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={markAll}
                disabled={busy}
                className="h-7 gap-1 text-xs"
              >
                {busy ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <CheckCheck className="h-3 w-3" />
                )}
                {t("markAllRead")}
              </Button>
            )}
          </div>
          {items === null ? (
            <div className="grid place-items-center py-8">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          ) : items.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">
              {t("empty")}
            </p>
          ) : (
            <ul className="max-h-[400px] divide-y overflow-y-auto">
              {items.map((n) => (
                <li
                  key={n.id}
                  className={cn(
                    "group flex cursor-pointer items-start gap-2 px-3 py-2.5 text-sm transition-colors hover:bg-muted/60",
                    !n.read_at && "bg-primary/5",
                  )}
                  onClick={() => click(n)}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      {!n.read_at && (
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                      )}
                      <span className="truncate font-medium">{n.title}</span>
                    </div>
                    {n.body && (
                      <div className="mt-0.5 truncate text-xs text-muted-foreground">
                        {n.body}
                      </div>
                    )}
                    <div className="mt-1 text-xs text-muted-foreground">
                      {formatWhen(n.created_at)}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => dismiss(n, e)}
                    aria-label={t("dismiss")}
                    className="invisible mt-1 rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive group-hover:visible"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function formatWhen(iso: string): string {
  try {
    const d = new Date(iso);
    const now = Date.now();
    const diffMin = Math.round((now - d.getTime()) / 60_000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffMin < 60 * 24) return `${Math.round(diffMin / 60)}h ago`;
    return d.toLocaleDateString();
  } catch {
    return iso;
  }
}
