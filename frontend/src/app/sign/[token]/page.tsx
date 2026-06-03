import { redirect } from "next/navigation";
import { defaultLocale } from "@/i18n/config";

/**
 * Top-level redirect shim for `/sign/{token}`.
 *
 * The backend's manual signing provider builds links as
 * `{frontend_base_url}/sign/{token}` (no locale prefix), and the
 * token contains a `.` (`{org_hex}.{secret}`) which makes the
 * next-intl middleware skip it (its matcher treats dotted paths as
 * static files), so it never gets the automatic locale redirect.
 * This static route catches the bare path and forwards to the
 * localized signing page, which lives under `[locale]/sign/[token]`.
 */
export default async function SignRedirect({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  redirect(`/${defaultLocale}/sign/${token}`);
}
