import type { ContractStatus } from "@/lib/api";

export const STATUS_VARIANT: Record<
  ContractStatus,
  "secondary" | "warning" | "success" | "danger" | "outline"
> = {
  draft: "secondary",
  sent: "warning",
  signed: "success",
  active: "success",
  terminated: "danger",
  expired: "outline",
};
