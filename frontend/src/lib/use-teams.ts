"use client";

/**
 * TanStack Query hooks for Teams. Two reads (teams + org members) and four
 * mutations that all invalidate the teams list.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Team, type TeamMember } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const teamsKeys = {
  all: ["teams"] as const,
  list: ["teams", "list"] as const,
  members: ["teams", "members"] as const,
};

export function useTeams() {
  const token = getToken();
  return useQuery<Team[]>({
    queryKey: teamsKeys.list,
    enabled: !!token,
    queryFn: () => api.listTeams(),
  });
}

export function useOrgMembers() {
  const token = getToken();
  return useQuery<TeamMember[]>({
    queryKey: teamsKeys.members,
    enabled: !!token,
    queryFn: () => api.listOrgMembers(),
  });
}

function useTeamsMutation<T>(fn: (a: T) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => qc.invalidateQueries({ queryKey: teamsKeys.list }),
  });
}

export function useCreateTeam() {
  return useTeamsMutation((name: string) => api.createTeam(name));
}

export function useDeleteTeam() {
  return useTeamsMutation((id: string) => api.deleteTeam(id));
}

export function useAddTeamMember() {
  return useTeamsMutation((a: { teamId: string; userId: string }) =>
    api.addTeamMember(a.teamId, a.userId),
  );
}

export function useRemoveTeamMember() {
  return useTeamsMutation((a: { teamId: string; userId: string }) =>
    api.removeTeamMember(a.teamId, a.userId),
  );
}
