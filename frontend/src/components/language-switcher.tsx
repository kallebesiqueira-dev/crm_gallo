"use client";

import { useRouter, usePathname } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Globe } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@radix-ui/react-dropdown-menu";
import { Button } from "@/components/ui/button";
import { locales, localeLabels, type Locale } from "@/i18n/config";

export function LanguageSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const current = useLocale() as Locale;
  const t = useTranslations("common");

  const switchTo = (target: Locale) => {
    if (!pathname) return;
    const segments = pathname.split("/");
    segments[1] = target;
    router.push(segments.join("/"));
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-2">
          <Globe className="h-4 w-4" />
          {localeLabels[current]}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={6}
        className="z-50 min-w-[10rem] overflow-hidden rounded-md border bg-popover bg-background p-1 shadow-md"
      >
        <div className="px-2 py-1.5 text-xs text-muted-foreground">{t("language")}</div>
        {locales.map((loc) => (
          <DropdownMenuItem
            key={loc}
            onSelect={() => switchTo(loc)}
            className="cursor-pointer rounded-sm px-2 py-1.5 text-sm outline-none hover:bg-accent data-[highlighted]:bg-accent"
          >
            {localeLabels[loc]}
            {loc === current && <span className="ml-2 text-xs text-muted-foreground">●</span>}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
