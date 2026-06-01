"use client";
import { useTranslations } from "next-intl";
import { PlaceholderPage } from "@/components/placeholder-page";

export default function Page() {
  const t = useTranslations("nav");
  return <PlaceholderPage title={t("documents")} />;
}
