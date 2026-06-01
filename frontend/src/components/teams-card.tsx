"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Plus, ShieldAlert, Trash2, Users, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type Team } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Admin/manager-only team management card on /settings.
 *
 * Capabilities (v1):
 *   - List teams in the current org + their members
 *   - Create a new team (auto-slug from name)
 *   - Soft-delete a team (members unassigned, leads/deals keep their
 *     data, just with team_id cleared)
 *   - Remove a member from a team
 *
 * Out of scope here (follow-ups): inline rename, slug-edit form,
 * adding members (requires a user-picker — defer until we have a
 * proper /users listing endpoint), reassigning users between teams.
 *
 * The backend enforces the role check; this component just shows
 * a friendly "admin/manager only" notice when the API 403s.
 */
interface Props {
  canManage: boolean;
}

export function TeamsCard({ canManage }: Props) {
  const t = useTranslations("teams");
  const [teams, setTeams] = useState<Team[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  async function refresh() {
    try {
      setTeams(await api.listTeams());
      setError(null);
    } catch (e) {
      // 403 → non-privileged user landed here; show friendly notice.
      if (e instanceof Error && e.message.toLowerCase().includes("insufficient role")) {
        setTeams([]);
      } else {
        setError(e instanceof Error ? e.message : "Load failed");
      }
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setCreating(true);
    setError(null);
    try {
      await api.createTeam(name);
      setNewName("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  async function remove(team: Team) {
    if (!confirm(t("confirmDelete", { name: team.name }))) return;
    setPendingDelete(team.id);
    setError(null);
    try {
      await api.deleteTeam(team.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setPendingDelete(null);
    }
  }

  async function unassign(team: Team, userId: string) {
    if (!confirm(t("confirmUnassign"))) return;
    setError(null);
    try {
      await api.removeTeamMember(team.id, userId);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Remove failed");
    }
  }

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="h-4 w-4" />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {!canManage && (
          <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-900 dark:text-amber-200">
            <ShieldAlert className="h-4 w-4" />
            {t("adminOnly")}
          </div>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        {canManage && (
          <form onSubmit={create} className="flex items-end gap-2">
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="new_team_name">{t("nameLabel")}</Label>
              <Input
                id="new_team_name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder={t("namePlaceholder")}
                required
              />
            </div>
            <Button type="submit" disabled={creating || !newName.trim()}>
              {creating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              {t("create")}
            </Button>
          </form>
        )}

        {teams === null ? (
          <div className="grid place-items-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : teams.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ul className="space-y-3">
            {teams.map((team) => (
              <li key={team.id} className="rounded-md border p-3">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <div>
                    <div className="font-medium">{team.name}</div>
                    <div className="text-xs text-muted-foreground">
                      <code className="font-mono">{team.slug}</code>
                      {" · "}
                      {t("memberCount", { count: team.member_count })}
                    </div>
                  </div>
                  {canManage && (
                    <button
                      type="button"
                      onClick={() => remove(team)}
                      disabled={pendingDelete === team.id}
                      aria-label={t("delete")}
                      className={cn(
                        "rounded-md border border-transparent p-1.5 text-muted-foreground transition-colors",
                        "hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive",
                      )}
                    >
                      {pendingDelete === team.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5" />
                      )}
                    </button>
                  )}
                </div>
                {team.members.length > 0 ? (
                  <ul className="flex flex-wrap gap-1.5">
                    {team.members.map((m) => (
                      <li
                        key={m.user_id}
                        className="flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs"
                      >
                        <span>{m.full_name}</span>
                        {canManage && (
                          <button
                            type="button"
                            onClick={() => unassign(team, m.user_id)}
                            aria-label={t("removeMember")}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-muted-foreground">{t("noMembers")}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
