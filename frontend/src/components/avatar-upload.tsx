"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useToast } from "@/components/toast-provider";

/**
 * Shrink an image to <=512px on its longest side and re-encode as JPEG before
 * upload: phone photos are multi-MB and were silently exceeding the server's
 * size limit (the upload failed and the avatar never saved). Falls back to the
 * original file if the canvas path isn't available so the upload still tries.
 */
async function downscaleImage(file: File): Promise<File> {
  if (!file.type.startsWith("image/")) return file;
  try {
    const bitmap = await createImageBitmap(file);
    const max = 512;
    const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
    const w = Math.max(1, Math.round(bitmap.width * scale));
    const h = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, w, h);
    bitmap.close?.();
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.85),
    );
    return blob ? new File([blob], "avatar.jpg", { type: "image/jpeg" }) : file;
  } catch {
    return file;
  }
}

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
  const toast = useToast();

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
      const upload = await downscaleImage(file);
      const r = await api.uploadAvatar(entityType, entityId, upload);
      setUrl(r.url);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Upload failed", "error");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

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
      <input ref={inputRef} type="file" accept="image/*" onChange={onFile} className="hidden" />
    </button>
  );
}
