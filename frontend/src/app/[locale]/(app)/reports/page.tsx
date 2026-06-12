import { redirect } from "next/navigation";

/**
 * Reports merged into the Performance screen as its "Report" tab
 * (skills.md §4) — keep old bookmarks/deep-links working.
 */
export default async function ReportsRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect(`/${locale}/performance?tab=reports`);
}
