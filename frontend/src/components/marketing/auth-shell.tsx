"use client";

import { useTranslations } from "next-intl";
import { LanguageSwitcher } from "@/components/language-switcher";
import { Logo } from "@/components/logo";
import { FuturisticBackground } from "@/components/marketing/futuristic-background";

/**
 * Unified auth shell. Now shares the exact same dark/violet futuristic
 * surface as the marketing landing: the page is forced dark and the
 * <FuturisticBackground> mesh flows under both the brand visual (left) and
 * the form (right) — one seamless plane, no bright/dark split. No theme
 * toggle here (the surface is intentionally always dark, like the landing).
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
    <div className="dark relative min-h-screen bg-[#040509] text-foreground">
      <FuturisticBackground />

      <div className="relative z-10 flex min-h-screen flex-col">
        {/* Top bar */}
        <header className="flex items-center justify-between px-6 py-5 sm:px-10">
          <Logo href="/" size="md" label={tApp("name")} />
          <LanguageSwitcher />
        </header>

        {/* Two columns share the same background. The form is frosted glass. */}
        <main className="mx-auto grid w-full max-w-6xl flex-1 items-center gap-12 px-6 py-8 sm:px-10 lg:grid-cols-2 lg:gap-16 lg:py-12">
          {/* Brand / visual side */}
          <section className="hidden flex-col justify-center lg:flex">{brand}</section>

          {/* Form side — frosted glass card on the same mesh */}
          <section className="flex items-center justify-center">
            <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/[0.04] p-8 shadow-2xl shadow-violet-950/40 backdrop-blur-xl">
              {children}
            </div>
          </section>
        </main>

        <footer className="px-6 py-6 text-center text-xs text-muted-foreground sm:px-10">
          © {new Date().getFullYear()} {tApp("name")} · AGPL-3.0
        </footer>
      </div>
    </div>
  );
}
