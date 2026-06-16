"use client";

import { Coins } from "lucide-react";
import { useCurrency, CURRENCIES } from "@/components/currency-provider";

/**
 * Compact display-currency picker for the top bar (EUR/CHF/USD/GBP). Changing
 * it converts the dashboard's money headlines client-side and persists the
 * choice on the user (see CurrencyProvider).
 */
export function CurrencySwitcher() {
  const { currency, setCurrency } = useCurrency();
  return (
    <div className="relative inline-flex items-center text-muted-foreground transition hover:text-foreground">
      <Coins className="pointer-events-none absolute left-2 h-4 w-4" />
      <select
        aria-label="Display currency"
        title="Display currency"
        value={currency}
        onChange={(e) => setCurrency(e.target.value as typeof currency)}
        className="h-9 cursor-pointer appearance-none rounded-lg bg-transparent pl-7 pr-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {CURRENCIES.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    </div>
  );
}
