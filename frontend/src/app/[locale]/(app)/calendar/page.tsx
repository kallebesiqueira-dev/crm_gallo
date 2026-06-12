import { redirect } from "next/navigation";

/**
 * The standalone calendar merged into Tasks as its month view
 * (skills.md §4) — keep old bookmarks/deep-links working.
 */
export default async function CalendarRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect(`/${locale}/tasks?view=month`);
}
