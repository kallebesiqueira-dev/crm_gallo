"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Plus, Trash2, Users2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useConfirm } from "@/components/confirm-dialog";
import { api, type Team, type TeamMember } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function TeamsPage() {
  const t = useTranslations("teams");
  const tCommon = useTranslations("common");
  const confirm = useConfirm();
  const [teams, setTeams] = useState<Team[]>([]);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [ts, ms] = await Promise.all([api.listTeams(), api.listOrgMembers()]);
      setTeams(ts);
      setMembers(ms);
      setLoading(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
      setLoading(false);
    }
  }

  useEffect(() => {
    if (getToken()) load();
  }, []);

  async function createTeam() {
    if (!newName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.createTeam(newName.trim());
      setNewName("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function deleteTeam(team: Team) {
    const ok = await confirm({ title: tCommon("confirmDelete"), tone: "danger", confirmLabel: tCommon("delete") });
    if (!ok) return;
    setError(null);
    try {
      await api.deleteTeam(team.id);
      setTeams((prev) => prev.filter((x) => x.id !== team.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  async function addMember(team: Team, userId: string) {
    if (!userId) return;
    setError(null);
    try {
      const updated = await api.addTeamMember(team.id, userId);
      setTeams((prev) => prev.map((x) => (x.id === team.id ? updated : x)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  async function removeMember(team: Team, userId: string) {
    setError(null);
    try {
      await api.removeTeamMember(team.id, userId);
      setTeams((prev) =>
        prev.map((x) =>
          x.id === team.id ? { ...x, members: x.members.filter((m) => m.user_id !== userId) } : x,
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      <Card className="flex flex-wrap items-center gap-2 p-4">
        <Input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && createTeam()}
          placeholder={t("newTeamName")}
          className="max-w-xs"
        />
        <Button type="button" onClick={createTeam} disabled={busy || !newName.trim()} className="gap-1.5">
          <Plus className="h-4 w-4" />
          {t("create")}
        </Button>
      </Card>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="space-y-3 p-4">
              <div className="flex items-center justify-between gap-2">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-4 w-4 rounded" />
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Skeleton className="h-5 w-20 rounded-full" />
                <Skeleton className="h-5 w-24 rounded-full" />
              </div>
            </Card>
          ))}
        </div>
      ) : teams.length === 0 ? (
        <Card className="p-10 text-center text-sm text-muted-foreground">{t("noTeams")}</Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {teams.map((team) => {
            const available = members.filter((m) => !team.members.some((tm) => tm.user_id === m.user_id));
            return (
              <Card key={team.id} className="space-y-3 p-4">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 font-semibold">
                    <Users2 className="h-4 w-4 text-primary" />
                    {team.name}
                    <span className="text-xs font-normal text-muted-foreground">
                      · {team.members.length}
                    </span>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={tCommon("delete")}
                    onClick={() => deleteTeam(team)}
                    className="text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {team.members.length === 0 ? (
                    <span className="text-xs text-muted-foreground">{t("noMembers")}</span>
                  ) : (
                    team.members.map((m) => (
                      <span
                        key={m.user_id}
                        className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
                      >
                        {m.full_name}
                        <button
                          type="button"
                          aria-label={tCommon("delete")}
                          onClick={() => removeMember(team, m.user_id)}
                          className="rounded-full p-0.5 hover:bg-primary/20"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))
                  )}
                </div>

                {available.length > 0 && (
                  <Select
                    value=""
                    onChange={(e) => addMember(team, e.target.value)}
                    aria-label={t("addMember")}
                  >
                    <option value="">{t("addMember")}</option>
                    {available.map((m) => (
                      <option key={m.user_id} value={m.user_id}>
                        {m.full_name}
                      </option>
                    ))}
                  </Select>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
