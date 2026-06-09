"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

/**
 * Round avatar that doubles as an upload control: it fetches the current photo
 * (a fresh presigned URL) on mount, and clicking it opens the file picker and
 * uploads the chosen image. Used for customers, companies and the current user.
 */
export function AvatarUpload({
  entityType,
  entityId,
  fallback,
  size = 80,
}: {
  entityType: "customer" | "company" | "user";
  entityId: string;
  fallback: string;
  size?: number;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

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

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const r = await api.uploadAvatar(entityType, entityId, file);
      setUrl(r.url);
    } catch {
      /* surfaced by the disabled state resetting; keep the old photo */
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  const badge = Math.max(14, Math.round(size / 3));
  return (
    <button
      type="button"
      onClick={() => inputRef.current?.click()}
      disabled={busy}
      aria-label="Change photo"
      title="Change photo"
      className="group relative shrink-0"
      style={{ width: size, height: size }}
    >
      <span className="relative block h-full w-full overflow-hidden rounded-full ring-2 ring-border">
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt="" className="h-full w-full object-cover" />
        ) : (
          <span
            className="grid h-full w-full place-items-center bg-gradient-to-br from-violet-500 to-fuchsia-500 font-semibold text-white"
            style={{ fontSize: size / 2.6 }}
          >
            {fallback}
          </span>
        )}
        <span className="absolute inset-0 grid place-items-center bg-black/40 opacity-0 transition group-hover:opacity-100">
          {busy ? (
            <Loader2 className="h-5 w-5 animate-spin text-white" />
          ) : (
            <Camera className="h-5 w-5 text-white" />
          )}
        </span>
      </span>
      {/* Always-visible camera badge so it's obvious the photo is editable */}
      <span
        className="absolute -bottom-0.5 -right-0.5 grid place-items-center rounded-full bg-primary text-primary-foreground ring-2 ring-background"
        style={{ width: badge, height: badge }}
      >
        <Camera style={{ width: Math.max(8, Math.round(size / 5)), height: Math.max(8, Math.round(size / 5)) }} />
      </span>
      <input ref={inputRef} type="file" accept="image/*" onChange={onFile} className="hidden" />
    </button>
  );
}
