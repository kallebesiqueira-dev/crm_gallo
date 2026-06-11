"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MfaCard } from "@/components/mfa-card";
import { SessionsCard } from "@/components/sessions-card";
import { TeamCard } from "@/components/team-card";
import { PipelinesCard } from "@/components/pipelines-card";
import { TeamsCard } from "@/components/teams-card";
import { DocumentTemplatesCard } from "@/components/document-templates-card";
import { CustomFieldsCard } from "@/components/custom-fields-card";
import { TagsCard } from "@/components/tags-card";
import { ApiKeysCard } from "@/components/api-keys-card";
import { WebhooksCard } from "@/components/webhooks-card";
import { api, type User } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { locales, localeLabels, type Locale } from "@/i18n/config";

export default function SettingsPage() {
  const t = useTranslations("settings");
  const tCommon = useTranslations("common");
  const tAuth = useTranslations("auth");
  const tLeads = useTranslations("leads");
  const router = useRouter();
  const currentLocale = useLocale();

  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [profileMsg, setProfileMsg] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileBusy, setProfileBusy] = useState(false);

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [localePref, setLocalePref] = useState<Locale>("en");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwdMsg, setPwdMsg] = useState<string | null>(null);
  const [pwdError, setPwdError] = useState<string | null>(null);
  const [pwdBusy, setPwdBusy] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api
      .me(token)
      .then((u) => {
        setUser(u);
        setFullName(u.full_name);
        setEmail(u.email);
        setLocalePref(u.locale as Locale);
      })
      .finally(() => setLoading(false));
  }, []);

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    const token = getToken();
    if (!token) return;
    setProfileBusy(true);
    setProfileMsg(null);
    setProfileError(null);
    try {
      const updated = await api.updateMe(token, {
        full_name: fullName,
        email,
        locale: localePref,
      });
      setUser(updated);
      setProfileMsg(tCommon("saved"));
      // If locale changed, navigate to new locale prefix
      if (updated.locale !== currentLocale) {
        const newPath = `/${updated.locale}/settings`;
        router.replace(newPath);
        router.refresh();
      }
    } catch (e) {
      setProfileError(e instanceof Error ? e.message : "Failed");
    } finally {
      setProfileBusy(false);
    }
  }

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    setPwdMsg(null);
    setPwdError(null);
    if (newPassword !== confirmPassword) {
      setPwdError(t("passwordMismatch"));
      return;
    }
    const token = getToken();
    if (!token) return;
    setPwdBusy(true);
    try {
      await api.changePassword(token, currentPassword, newPassword);
      setPwdMsg(t("passwordChanged"));
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (e) {
      setPwdError(e instanceof Error ? e.message : "Failed");
    } finally {
      setPwdBusy(false);
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">{tCommon("loading")}</p>;
  if (!user) return null;

  // Admins of the current org can invite. We check the legacy `user.role`
  // for now — Phase 2's `get_current_membership` is the server-side
  // source of truth, this is just a UX gate.
  const canInvite = user.role === "admin";
  // Templates seed contract boilerplate — admins + managers may author.
  const canManageTemplates = user.role === "admin" || user.role === "manager";

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>{t("profile")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={saveProfile} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="full_name">{tAuth("fullName")}</Label>
              <Input
                id="full_name"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">{tAuth("email")}</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="locale">{tCommon("language")}</Label>
              <select
                id="locale"
                aria-label={tCommon("language")}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={localePref}
                onChange={(e) => setLocalePref(e.target.value as Locale)}
              >
                {locales.map((l) => (
                  <option key={l} value={l}>
                    {localeLabels[l]}
                  </option>
                ))}
              </select>
            </div>
            <div className="text-xs text-muted-foreground">
              {t("role")}: <span className="font-medium text-foreground">{user.role}</span>
            </div>
            {profileMsg && <p className="text-sm text-emerald-600">{profileMsg}</p>}
            {profileError && <p className="text-sm text-destructive">{profileError}</p>}
            <Button type="submit" disabled={profileBusy}>
              {tLeads("save")}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("password")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={changePassword} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="current_password">{t("currentPassword")}</Label>
              <Input
                id="current_password"
                type="password"
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new_password">{t("newPassword")}</Label>
              <Input
                id="new_password"
                type="password"
                required
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm_password">{t("confirmPassword")}</Label>
              <Input
                id="confirm_password"
                type="password"
                required
                minLength={8}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>
            {pwdMsg && <p className="text-sm text-emerald-600">{pwdMsg}</p>}
            {pwdError && <p className="text-sm text-destructive">{pwdError}</p>}
            <Button type="submit" disabled={pwdBusy}>
              {t("changePassword")}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* 2FA — visible to every user, opt-in self-enrollment. */}
      <MfaCard />

      {/* Active sessions — list every device, revoke individuals or
          all-other-devices. The current session is flagged and its
          revoke button is disabled (use /logout to end it). */}
      <SessionsCard />

      {/* Team management — full-width below profile/password cards.
          Non-admins see the empty state + admin-only notice. */}
      <TeamCard canInvite={canInvite} />

      {/* Team management — create / soft-delete teams, see members.
          Adding members is a follow-up (needs a user-picker). Backend
          gates mutation to admin/manager; the card surfaces a friendly
          notice when the current user can't manage. */}
      <TeamsCard canManage={canInvite} />

      {/* Pipeline editor — customise the lead + deal funnels. Phase 1
          ships the editor + auto-seeded defaults; Phase 2 will wire
          Lead/Deal.stage to pipeline_stage_id so changes here flow
          to the kanban + list filters. Same admin/manager gating. */}
      <PipelinesCard canManage={canInvite} />

      {/* Merge-field document templates — author reusable contract
          bodies with {{ token }} placeholders. Admin/manager gated. */}
      <DocumentTemplatesCard canManage={canManageTemplates} />

      {/* Custom-field schema editor — declare per-entity custom fields
          that then appear on every create/edit form. Admin/manager gated. */}
      <CustomFieldsCard canManage={canManageTemplates} />

      {/* Org-wide tag catalogue — any member can add tags; rename/recolour/
          delete is admin/manager gated (they change the tag for everyone). */}
      <TagsCard canManage={canManageTemplates} />

      {/* Public-API bearer keys — mint / revoke server-to-server
          credentials for /api/v1. Admin-only (creation requires admin);
          the card shows a notice + hides actions for non-admins. */}
      <ApiKeysCard canManage={canInvite} />

      {/* Webhook endpoints — HTTP POST delivery to external servers,
          HMAC-signed per-endpoint. Admin-only creation/deletion. */}
      <WebhooksCard canManage={canInvite} />
    </div>
  );
}
