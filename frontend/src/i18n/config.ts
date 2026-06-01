export const locales = ["en", "de", "fr", "it", "rm", "pt", "es"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "en";

export const localeLabels: Record<Locale, string> = {
  en: "English",
  de: "Deutsch",
  fr: "Français",
  it: "Italiano",
  rm: "Rumantsch",
  pt: "Português",
  es: "Español",
};
