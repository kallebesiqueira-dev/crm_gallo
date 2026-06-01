"use client";

import { cn } from "@/lib/utils";

interface TooltipPayloadItem {
  name?: string;
  value?: number | string;
  color?: string;
  dataKey?: string;
  payload?: Record<string, unknown>;
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string | number;
  valueFormatter?: (n: number) => string;
  className?: string;
}

/**
 * Themed tooltip that respects light/dark via CSS vars. Recharts injects
 * `active`, `payload`, `label` via the <Tooltip content={ChartTooltip}/> prop.
 */
export function ChartTooltip({
  active,
  payload,
  label,
  valueFormatter,
  className,
}: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div
      className={cn(
        "rounded-lg border bg-popover px-3 py-2 text-xs shadow-lg backdrop-blur",
        className,
      )}
    >
      {label !== undefined && (
        <div className="mb-1 font-medium text-foreground">{label}</div>
      )}
      <div className="space-y-1">
        {payload.map((p, i) => (
          <div key={i} className="flex items-center gap-2">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: p.color ?? "currentColor" }}
            />
            <span className="text-muted-foreground">{p.name ?? p.dataKey}</span>
            <span className="ml-auto font-mono text-foreground">
              {typeof p.value === "number" && valueFormatter
                ? valueFormatter(p.value)
                : String(p.value ?? "")}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
