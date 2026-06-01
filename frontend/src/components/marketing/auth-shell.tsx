"use client";

import { useTranslations } from "next-intl";
import { ThemeToggle } from "@/components/theme-toggle";
import { LanguageSwitcher } from "@/components/language-switcher";
import { Logo } from "@/components/logo";

/**
 * Unified auth shell. Same background flows under both the marketing copy
 * (left/top) and the form (right/bottom) — no hard split between bright
 * brand panel and dark form. The "1% engineer" look: gradient mesh blobs
 * scattered behind a single seamless surface.
 */
export function AuthShell({
  brand,
  children,
}: {
  brand: React.ReactNode;
  children: React.ReactNode;
}) {
  const tApp = useTranslations("app");

  return (
    <div className="relative min-h-screen overflow-hidden bg-background">
      {/* Background mesh — same plane covers the whole viewport */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-40 left-[10%] h-[480px] w-[480px] rounded-full bg-blue-500/25 blur-[120px] dark:bg-blue-500/15" />
        <div className="absolute top-[20%] right-[5%] h-[420px] w-[420px] rounded-full bg-violet-500/25 blur-[120px] dark:bg-violet-500/15" />
        <div className="absolute -bottom-32 left-[30%] h-[420px] w-[420px] rounded-full bg-fuchsia-500/20 blur-[120px] dark:bg-fuchsia-500/12" />
      </div>

      {/* Top bar */}
      <header className="relative flex items-center justify-between px-6 py-5 sm:px-10">
        <Logo href="/" size="md" label={tApp("name")} />
        <div className="flex items-center gap-2">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
      </header>

      {/* Two columns share the same background. The form card has frosted glass. */}
      <main className="relative mx-auto grid w-full max-w-6xl gap-12 px-6 py-8 sm:px-10 lg:grid-cols-2 lg:gap-16 lg:py-16">
        {/* Brand / copy side */}
        <section className="hidden flex-col justify-center lg:flex">{brand}</section>

        {/* Form side — frosted glass card on the same background */}
        <section className="flex items-center justify-center">
          <div className="w-full max-w-md rounded-2xl border bg-card/70 p-8 shadow-2xl shadow-primary/10 backdrop-blur-xl">
            {children}
          </div>
        </section>
      </main>

      <footer className="relative px-6 py-6 text-center text-xs text-muted-foreground sm:px-10">
        © {new Date().getFullYear()} {tApp("name")} · AGPL-3.0
      </footer>
    </div>
  );
}
