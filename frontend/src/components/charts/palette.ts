/**
 * Chart color palette — designer-tuned for high readability on light and dark.
 * Hue order roughly follows a sales-funnel feel: cool → warm → success.
 */

export const CHART_COLORS = {
  blue: "#3b82f6",
  cyan: "#06b6d4",
  teal: "#14b8a6",
  emerald: "#10b981",
  lime: "#84cc16",
  amber: "#f59e0b",
  orange: "#f97316",
  red: "#ef4444",
  rose: "#f43f5e",
  fuchsia: "#d946ef",
  violet: "#8b5cf6",
  indigo: "#6366f1",
} as const;

export const STAGE_COLORS: Record<string, string> = {
  new: CHART_COLORS.indigo,
  contacted: CHART_COLORS.cyan,
  qualified: CHART_COLORS.teal,
  proposal_sent: CHART_COLORS.amber,
  negotiation: CHART_COLORS.orange,
  won: CHART_COLORS.emerald,
  lost: CHART_COLORS.red,
};

export const CURRENCY_COLORS: Record<string, string> = {
  EUR: CHART_COLORS.blue,
  CHF: CHART_COLORS.violet,
  USD: CHART_COLORS.emerald,
  GBP: CHART_COLORS.fuchsia,
};

/** Cycles through a colorful sequence regardless of input size. */
export function rotatingColor(i: number): string {
  const order = [
    CHART_COLORS.blue,
    CHART_COLORS.emerald,
    CHART_COLORS.amber,
    CHART_COLORS.violet,
    CHART_COLORS.cyan,
    CHART_COLORS.rose,
    CHART_COLORS.teal,
    CHART_COLORS.orange,
  ];
  return order[i % order.length];
}
