"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Read-only avatar for lists/cards: fetches the entity's photo (a presigned
 * URL) on mount and shows it, falling back to initials on the brand gradient.
 * Unlike <AvatarUpload> it's not a button, so it's safe to nest inside a
 * <Link>. One small GET per instance — fine for short recent-item lists.
 */
export function EntityAvatar({
  entityType,
  entityId,
  fallback,
  size = 36,
  className,
}: {
  entityType: "customer" | "company" | "user";
  entityId: string;
  fallback: string;
  size?: number;
  className?: string;
}) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    api
      .getAvatar(entityType, entityId)
      .then((r) => {
        if (!stop) setUrl(r.url);
      })
      .catch(() => {});
    return () => {
      stop = true;
    };
  }, [entityType, entityId]);

  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center overflow-hidden rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 font-bold text-white",
        className,
      )}
      style={{ width: size, height: size, fontSize: size / 2.6 }}
    >
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className="h-full w-full object-cover" />
      ) : (
        fallback
      )}
    </span>
  );
}
