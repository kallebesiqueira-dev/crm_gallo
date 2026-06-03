import type { QuoteStatus } from "@/lib/api";

export const STATUS_VARIANT: Record<
  QuoteStatus,
  "secondary" | "warning" | "success" | "danger" | "outline"
> = {
  draft: "secondary",
  sent: "warning",
  accepted: "success",
  declined: "danger",
  expired: "outline",
};
