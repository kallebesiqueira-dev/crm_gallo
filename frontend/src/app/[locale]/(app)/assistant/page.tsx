import { redirect } from "next/navigation";

/**
 * The assistant is a global slide-out now (top-bar ✨ button on every
 * screen — skills.md §4 rework), not a page. Keep old links working.
 */
export default async function AssistantRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect(`/${locale}/dashboard`);
}
