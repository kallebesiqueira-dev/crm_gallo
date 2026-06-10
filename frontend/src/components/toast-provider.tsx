"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

type Variant = "default" | "success" | "error" | "warning";

interface Toast {
  id: string;
  message: string;
  variant: Variant;
}

interface ToastContextValue {
  toast: (message: string, variant?: Variant) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let externalToast: ((message: string, variant?: Variant) => void) | null = null;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (message: string, variant: Variant = "default") => {
      const id = Math.random().toString(36).slice(2);
      setToasts((prev) => [...prev.slice(-4), { id, message, variant }]);
      setTimeout(() => dismiss(id), 4000);
    },
    [dismiss]
  );

  // Expose for imperative use outside React (e.g. api.ts catch blocks)
  useEffect(() => {
    externalToast = toast;
    return () => { externalToast = null; };
  }, [toast]);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-[100] flex flex-col-reverse gap-2"
      >
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({
  toast: t,
  onDismiss,
}: {
  toast: Toast;
  onDismiss: (id: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.opacity = "0";
    el.style.transform = "translateY(8px)";
    requestAnimationFrame(() => {
      el.style.transition = "opacity 150ms, transform 150ms";
      el.style.opacity = "1";
      el.style.transform = "translateY(0)";
    });
  }, []);

  return (
    <div
      ref={ref}
      className={cn(
        "pointer-events-auto flex items-start gap-3 rounded-lg border px-4 py-3 shadow-lg",
        "min-w-[260px] max-w-[380px] text-sm",
        t.variant === "error" &&
          "border-destructive/40 bg-destructive/10 text-destructive",
        t.variant === "success" &&
          "border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-400",
        t.variant === "warning" &&
          "border-yellow-500/40 bg-yellow-500/10 text-yellow-700 dark:text-yellow-400",
        (t.variant === "default" || !t.variant) &&
          "border bg-background text-foreground"
      )}
    >
      <span className="flex-1 leading-snug">{t.message}</span>
      <button
        type="button"
        onClick={() => onDismiss(t.id)}
        aria-label="Dismiss"
        className="mt-0.5 shrink-0 opacity-60 hover:opacity-100"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx.toast;
}

/** Imperative toast for use outside React components (catch blocks in api.ts). */
export function showToast(message: string, variant: Variant = "default") {
  externalToast?.(message, variant);
}
