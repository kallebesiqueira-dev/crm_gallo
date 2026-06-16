"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { api, type Currency } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const CURRENCIES: Currency[] = ["EUR", "CHF", "USD", "GBP"];

type CurrencyCtx = {
  currency: Currency;
  setCurrency: (c: Currency) => void;
  /** Format an EUR-denominated amount in the active display currency. */
  format: (eurAmount: number) => string;
  ready: boolean;
};

const Ctx = createContext<CurrencyCtx | null>(null);

/**
 * Display-currency layer (roadmap #1). Stored money is always EUR; this
 * converts for *display* only, client-side, using EUR-based rates from
 * /api/fx/rates (1 EUR = rates[ccy]). The choice persists on the user
 * (PATCH /api/auth/me display_currency) so it follows them across devices.
 */
export function CurrencyProvider({
  initial,
  locale,
  children,
}: {
  initial: Currency;
  locale: string;
  children: React.ReactNode;
}) {
  const [currency, setCurrencyState] = useState<Currency>(initial);
  const [rates, setRates] = useState<Record<string, number> | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let stop = false;
    api
      .getFxRates(token)
      .then((r) => {
        if (!stop) setRates(r.rates);
      })
      .catch(() => {
        /* rates are non-critical — fall back to showing EUR */
      });
    return () => {
      stop = true;
    };
  }, []);

  const setCurrency = useCallback((c: Currency) => {
    setCurrencyState(c);
    const token = getToken();
    // Persist the preference; non-blocking (the UI already switched).
    if (token) api.updateMe(token, { display_currency: c }).catch(() => {});
  }, []);

  const format = useCallback(
    (eurAmount: number) => {
      const rate = currency === "EUR" ? 1 : rates?.[currency];
      const ccy = rate ? currency : "EUR"; // until rates load, show EUR
      return new Intl.NumberFormat(locale, {
        style: "currency",
        currency: ccy,
        maximumFractionDigits: 0,
      }).format(eurAmount * (rate ?? 1));
    },
    [currency, rates, locale],
  );

  const value = useMemo<CurrencyCtx>(
    () => ({ currency, setCurrency, format, ready: rates !== null }),
    [currency, setCurrency, format, rates],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCurrency(): CurrencyCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useCurrency must be used inside <CurrencyProvider>");
  return ctx;
}
