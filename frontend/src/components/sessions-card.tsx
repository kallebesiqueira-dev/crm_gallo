"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, LogOut, Monitor, Smartphone, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type SessionInfo } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Active sessions panel — lists every device with a live refresh
 * token, lets the user revoke individual sessions or "sign out all
 * other devices" in one click. Current session is marked and its
 * revoke button is disabled (the backend rejects that path too —
 * /logout is the intended way to end your own session).
 */
export function SessionsCard() {
  const t = useTranslations("sessions");
  const [sessions, setSessions] = useState<SessionInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [revokingOthers, setRevokingOthers] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  async function refresh() {
    try {
      setSessions(await api.listSessions());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function revokeOne(s: SessionInfo) {
    if (s.current) return;
    if (!confirm(t("confirmRevoke", { device: deviceLabel(s.user_agent) }))) return;
    setPendingId(s.id);
    setBanner(null);
    try {
      await api.revokeSession(s.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Revoke failed");
    } finally {
      setPendingId(null);
    }
  }

  async function revokeOthers() {
    if (!sessions || sessions.length <= 1) return;
    if (!confirm(t("confirmRevokeOthers"))) return;
    setRevokingOthers(true);
    setBanner(null);
    try {
      const res = await api.revokeOtherSessions();
      setBanner(t("revokedOthers", { count: res.revoked }));
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Revoke failed");
    } finally {
      setRevokingOthers(false);
    }
  }

  const othersCount = (sessions ?? []).filter((s) => !s.current).length;

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Monitor className="h-4 w-4" />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && <p className="text-sm text-destructive">{error}</p>}
        {banner && (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
            {banner}
          </div>
        )}
        {sessions === null ? (
          <div className="grid place-items-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            <ul className="divide-y rounded-md border">
              {sessions.map((s) => (
                <li
                  key={s.id}
                  className="flex items-start justify-between gap-3 px-3 py-3 text-sm"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 font-medium">
                      {isMobile(s.user_agent) ? (
                        <Smartphone className="h-3.5 w-3.5 text-muted-foreground" />
                      ) : (
                        <Monitor className="h-3.5 w-3.5 text-muted-foreground" />
                      )}
                      <span>{deviceLabel(s.user_agent)}</span>
                      {s.current && (
                        <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                          {t("currentBadge")}
                        </span>
                      )}
                    </div>
                    <div className="mt-1 grid gap-0.5 text-xs text-muted-foreground">
                      <span>
                        {t("ip")}: <span className="font-mono">{s.ip_address || "—"}</span>
                      </span>
                      {s.last_seen_at && (
                        <span>{t("lastSeen", { when: formatWhen(s.last_seen_at) })}</span>
                      )}
                      {s.created_at && (
                        <span>{t("signedIn", { when: formatWhen(s.created_at) })}</span>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => revokeOne(s)}
                    disabled={s.current || pendingId === s.id}
                    aria-label={t("revoke")}
                    className={cn(
                      "rounded-md border border-transparent p-1.5 text-muted-foreground transition-colors",
                      s.current
                        ? "cursor-not-allowed opacity-30"
                        : "hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive",
                    )}
                  >
                    {pendingId === s.id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <X className="h-3.5 w-3.5" />
                    )}
                  </button>
                </li>
              ))}
            </ul>
            {othersCount > 0 && (
              <div className="flex justify-end">
                <Button
                  variant="outline"
                  onClick={revokeOthers}
                  disabled={revokingOthers}
                >
                  <LogOut className="h-4 w-4" />
                  {revokingOthers
                    ? t("revokingOthers")
                    : t("revokeOthers", { count: othersCount })}
                </Button>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** Cheap UA → friendly device string. Not perfect — good enough for
 *  a list of sessions. Real device-detection libs are 10+ kB and a
 *  pile of regex; this keeps the bundle small.
 */
function deviceLabel(ua: string): string {
  if (!ua) return "Unknown device";
  const u = ua.toLowerCase();
  const browser =
    u.includes("firefox") ? "Firefox"
      : u.includes("edg/") ? "Edge"
      : u.includes("chrome") ? "Chrome"
      : u.includes("safari") ? "Safari"
      : "Browser";
  const os =
    u.includes("iphone") ? "iPhone"
      : u.includes("ipad") ? "iPad"
      : u.includes("android") ? "Android"
      : u.includes("mac os") ? "macOS"
      : u.includes("windows") ? "Windows"
      : u.includes("linux") ? "Linux"
      : "";
  return os ? `${browser} on ${os}` : browser;
}

function isMobile(ua: string): boolean {
  const u = ua.toLowerCase();
  return u.includes("iphone") || u.includes("ipad") || u.includes("android");
}

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
