"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Check, ChevronDown, Loader2, Plus } from "lucide-react";
import { api, type Membership } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

/**
 * Header dropdown that lists the user's org memberships and switches the
 * active one. Hidden entirely when the user has 0–1 memberships (the
 * single-tenant case stays clean — no UI for a feature that has no
 * meaning).
 *
 * Switching is a server-side write: `POST /api/orgs/me/switch` updates
 * `users.last_active_org_id`. We then trigger a hard reload because every
 * data-fetching screen needs to remount against the new tenant. A more
 * surgical refetch (React Query invalidation) becomes worthwhile only
 * once we have TanStack Query everywhere (P2 backlog).
 *
 * The "Create new organization" action calls `POST /api/orgs` which
 * auto-switches; same reload triggers afterwards.
 */
export function OrgSwitcher({
  activeOrgId,
}: {
  activeOrgId: string | null;
}) {
  const router = useRouter();
  const [memberships, setMemberships] = useState<Membership[] | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [createMode, setCreateMode] = useState(false);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.listMyOrgs(token).then(setMemberships).catch(() => setMemberships([]));
  }, []);

  // Loading skeleton — keep the chip width stable so the header doesn't
  // jump as memberships resolve.
  if (memberships === null) {
    return (
      <div className="grid h-8 w-32 place-items-center rounded-md border border-border bg-muted/40">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Single-tenant install — hide the switcher entirely. No "you only
  // have one org" pill cluttering the header.
  if (memberships.length <= 1) {
    return null;
  }

  const active =
    memberships.find((m) => m.organization.id === activeOrgId) ?? memberships[0];

  async function handleSwitch(orgId: string) {
    if (orgId === active.organization.id) {
      setOpen(false);
      return;
    }
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await api.switchOrg(token, orgId);
      // Hard reload — every CRUD/list/dashboard component pulls org-scoped
      // data at mount, so a full reload is the cheapest correct path. Move
      // to surgical refetch when TanStack Query lands.
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Switch failed");
      setBusy(false);
    }
  }

  async function handleCreate() {
    const name = newName.trim();
    if (!name) {
      setError("Name required");
      return;
    }
    const token = getToken();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await api.createOrg(token, name);
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
      setBusy(false);
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-background px-3 text-sm font-medium hover:bg-muted"
      >
        <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="max-w-[160px] truncate">{active.organization.name}</span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <>
          {/* Click-outside catcher — keeps the dropdown closing semantics
              dead simple without a Radix Popover dependency. */}
          <button
            type="button"
            aria-hidden
            className="fixed inset-0 z-30 cursor-default"
            onClick={() => {
              setOpen(false);
              setCreateMode(false);
              setError(null);
            }}
          />
          <div className="absolute right-0 z-40 mt-1 w-72 overflow-hidden rounded-md border border-border bg-popover shadow-lg">
            <div className="border-b border-border px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Switch organization
            </div>
            <ul className="max-h-72 overflow-y-auto py-1">
              {memberships.map((m) => {
                const isActive = m.organization.id === active.organization.id;
                return (
                  <li key={m.organization.id}>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => handleSwitch(m.organization.id)}
                      className={cn(
                        "flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-muted disabled:opacity-50",
                        isActive && "bg-muted/40",
                      )}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium">
                          {m.organization.name}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {m.role} · {m.organization.plan}
                        </div>
                      </div>
                      {isActive && <Check className="h-4 w-4 text-primary shrink-0" />}
                    </button>
                  </li>
                );
              })}
            </ul>

            <div className="border-t border-border">
              {createMode ? (
                <div className="space-y-2 p-3">
                  <input
                    autoFocus
                    type="text"
                    placeholder="Organization name"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleCreate();
                      if (e.key === "Escape") setCreateMode(false);
                    }}
                    className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    disabled={busy}
                  />
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setCreateMode(false);
                        setError(null);
                      }}
                      className="rounded-md px-3 py-1.5 text-xs hover:bg-muted"
                      disabled={busy}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleCreate}
                      disabled={busy || !newName.trim()}
                      className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                    >
                      {busy && <Loader2 className="h-3 w-3 animate-spin" />}
                      Create
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setCreateMode(true)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Create new organization
                </button>
              )}
              {error && (
                <p className="border-t border-border px-3 py-2 text-xs text-destructive">
                  {error}
                </p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
