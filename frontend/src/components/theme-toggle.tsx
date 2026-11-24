"use client";

import * as React from "react";
import { Moon, Sun } from "lucide-react";
import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const menuRow =
  "flex h-9 w-full items-center gap-2.5 rounded-lg px-2.5 text-sm text-foreground outline-none transition-colors hover:bg-accent focus-visible:bg-accent";

export function ThemeToggle({ variant = "icon" }: { variant?: "icon" | "menu" }) {
  const t = useTranslations("common");
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  const dark = mounted && resolvedTheme === "dark";

  if (variant === "menu") {
    return (
      <button
        type="button"
        onClick={() => setTheme(dark ? "light" : "dark")}
        className={menuRow}
        aria-label={t("theme")}
        aria-pressed={dark}
      >
        {dark ? (
          <Sun className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <Moon className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <span className="flex-1 text-left">{t("theme")}</span>
        <span
          aria-hidden
          className={cn(
            "relative h-5 w-9 shrink-0 rounded-full transition-colors",
            dark ? "bg-primary" : "bg-muted-foreground/25",
          )}
        >
          <span
            className={cn(
              "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform",
              dark ? "left-4" : "left-0.5",
            )}
          />
        </span>
      </button>
    );
  }

  if (!mounted) return <Button variant="ghost" size="icon" aria-label={t("theme")} />;

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      aria-label={t("theme")}
    >
      {resolvedTheme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}
