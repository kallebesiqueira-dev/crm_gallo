"use client";

import * as React from "react";
import { Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/utils";

export interface PasswordInputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  showStrength?: boolean;
  strengthLabels?: { weak: string; fair: string; good: string; strong: string };
  visibilityLabels?: { show: string; hide: string };
}

/**
 * Score 0–4 like zxcvbn-lite. Cheap heuristic — good enough for client-side
 * UX, never used as a server-side guarantee.
 */
function scorePassword(pw: string): number {
  if (!pw) return 0;
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++;
  if (/\d/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  return Math.min(4, score);
}

export const PasswordInput = React.forwardRef<HTMLInputElement, PasswordInputProps>(
  (
    {
      className,
      showStrength = false,
      strengthLabels = { weak: "Weak", fair: "Fair", good: "Good", strong: "Strong" },
      visibilityLabels = { show: "Show password", hide: "Hide password" },
      value,
      onChange,
      ...props
    },
    ref,
  ) => {
    const [visible, setVisible] = React.useState(false);
    const [internalValue, setInternalValue] = React.useState("");
    const currentValue = typeof value === "string" ? value : internalValue;

    const score = React.useMemo(() => scorePassword(currentValue), [currentValue]);
    const strengthLabel = ["", strengthLabels.weak, strengthLabels.fair, strengthLabels.good, strengthLabels.strong][
      score
    ];
    const strengthColor = [
      "bg-muted",
      "bg-red-500",
      "bg-amber-500",
      "bg-blue-500",
      "bg-emerald-500",
    ][score];

    return (
      <div className="space-y-2">
        <div className="relative">
          <input
            ref={ref}
            type={visible ? "text" : "password"}
            value={currentValue}
            onChange={(e) => {
              if (value === undefined) setInternalValue(e.target.value);
              onChange?.(e);
            }}
            className={cn(
              "flex h-10 w-full rounded-md border border-input bg-background pl-3 pr-10 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
              className,
            )}
            {...props}
          />
          <button
            type="button"
            tabIndex={-1}
            onClick={() => setVisible((v) => !v)}
            aria-label={visible ? visibilityLabels.hide : visibilityLabels.show}
            className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>

        {showStrength && currentValue.length > 0 && (
          <div className="space-y-1">
            <div className="flex gap-1">
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className={cn(
                    "h-1 flex-1 rounded-full transition-colors",
                    i <= score ? strengthColor : "bg-muted",
                  )}
                />
              ))}
            </div>
            <div className="text-xs text-muted-foreground">{strengthLabel}</div>
          </div>
        )}
      </div>
    );
  },
);
PasswordInput.displayName = "PasswordInput";
