"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { ArrowRight, Building2, Loader2, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { AuthShell } from "@/components/marketing/auth-shell";
import { api, type InvitePreview } from "@/lib/api";
import { setToken } from "@/lib/auth";

/**
 * /[locale]/invite/[token] — landing page for an invite link.
 *
 * Flow:
 *   1. Mount → `previewInvite(token)` resolves org name + email + role.
 *      404 / 410 surface as a friendly explainer (expired or already used);
 *      no register form is ever shown for a dead token.
 *   2. Valid token → render the registration form with email pinned
 *      (read-only) so the invitee can't repoint the invite at a
 *      different address.
 *   3. Submit → `registerWithInvite()` creates the user + membership
 *      atomically (backend handles the seat check). On success: store
 *      token, push to /[locale]/dashboard.
 */

interface PageProps {
  params: Promise<{ locale: string; token: string }>;
}

export default function InviteAcceptPage({ params }: PageProps) {
  const { token } = use(params);
  const tAuth = useTranslations("auth");
  const router = useRouter();
  const locale = useLocale();

  const [preview, setPreview] = useState<InvitePreview | null>(null);
  // Distinguishes "still loading" (null) from "preview tried, failed" (string).
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    api
      .previewInvite(token)
      .then((p) => {
        setPreview(p);
        setPreviewError(null);
      })
      .catch((e) => {
        // 404 = unknown token; 410 = expired or already used. Both
        // collapse to a single dead-link UX — the difference is only
        // useful for our logs, not the invitee.
        setPreviewError(
          e?.status === 410
            ? tAuth("inviteExpiredOrUsed")
            : tAuth("inviteNotFound"),
        );
      });
  }, [token, tAuth]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!preview) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await api.registerWithInvite({
        token,
        full_name: fullName.trim(),
        password,
        locale,
      });
      setToken(res.token.access_token);
      router.replace(`/${locale}/dashboard`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Registration failed");
      setSubmitting(false);
    }
  }

  // ── Loading state ────────────────────────────────────────────────
  if (preview === null && !previewError) {
    return (
      <AuthShell brand={<InviteBrand />}>
        <div className="grid place-items-center py-12 text-muted-foreground">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
      </AuthShell>
    );
  }

  // ── Dead link state ──────────────────────────────────────────────
  if (previewError) {
    return (
      <AuthShell brand={<InviteBrand />}>
        <div className="space-y-4 text-center">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-destructive/10 text-destructive">
            <ShieldAlert className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {tAuth("inviteUnavailable")}
          </h1>
          <p className="text-sm text-muted-foreground">{previewError}</p>
          <Button asChild variant="outline">
            <a href={`/${locale}/login`}>{tAuth("login")}</a>
          </Button>
        </div>
      </AuthShell>
    );
  }

  // ── Happy path: register form ────────────────────────────────────
  return (
    <AuthShell brand={<InviteBrand />}>
      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="space-y-1.5">
          <p className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-medium">
            <Building2 className="h-3 w-3 text-primary" />
            {preview!.organization_name}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">
            {tAuth("acceptInviteTitle")}
          </h1>
          <p className="text-sm text-muted-foreground">
            {tAuth("acceptInviteSubtitle", {
              role: preview!.role,
              org: preview!.organization_name,
            })}
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="email">{tAuth("email")}</Label>
          <Input id="email" type="email" value={preview!.email} readOnly disabled />
          <p className="text-xs text-muted-foreground">
            {tAuth("inviteEmailPinned")}
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="fullName">{tAuth("fullName")}</Label>
          <Input
            id="fullName"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder={tAuth("fullNamePlaceholder")}
            required
            autoFocus
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="password">{tAuth("password")}</Label>
          <PasswordInput
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
        </div>

        {submitError && (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {submitError}
          </div>
        )}

        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <>
              {tAuth("acceptAndJoin")}
              <ArrowRight className="h-4 w-4" />
            </>
          )}
        </Button>
      </form>
    </AuthShell>
  );
}

function InviteBrand() {
  const tAuth = useTranslations("auth");
  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
        {tAuth("inviteBrandTitle")}
      </h2>
      <p className="text-base text-muted-foreground">
        {tAuth("inviteBrandSubtitle")}
      </p>
    </div>
  );
}
