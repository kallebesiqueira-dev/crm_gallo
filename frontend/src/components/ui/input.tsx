import * as React from "react";
import { cn } from "@/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        // iOS Safari centers <input type=date> values by default; left-align the
        // WebKit value + edit fields so date pickers match the text inputs
        // (these pseudo-elements only exist on date/time inputs — no-op elsewhere).
        "[&::-webkit-date-and-time-value]:text-left [&::-webkit-datetime-edit]:text-left",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
