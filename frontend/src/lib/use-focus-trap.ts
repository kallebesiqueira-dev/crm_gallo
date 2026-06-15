import { useEffect, useRef } from "react";

type Options = {
  /** Called when Escape is pressed inside the dialog (omit to keep your own handler). */
  onEscape?: () => void;
  /** Element to focus when the dialog opens; falls back to the first focusable. */
  initialFocus?: React.RefObject<HTMLElement | null>;
};

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

/**
 * Accessible modal behaviour for a dialog container ref. While `open`:
 * moves focus into the dialog, traps Tab / Shift+Tab inside it, optionally
 * closes on Escape, and restores focus to the previously-focused element
 * (the trigger) when it closes. Callbacks are read through a ref, so passing
 * an inline/unstable `onEscape` does not re-run the effect.
 */
export function useFocusTrap(
  ref: React.RefObject<HTMLElement | null>,
  open: boolean,
  options: Options = {},
) {
  const optsRef = useRef(options);
  optsRef.current = options;

  useEffect(() => {
    if (!open) return;
    const node = ref.current;
    if (!node) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;

    const focusable = () =>
      Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null,
      );

    const initial = optsRef.current.initialFocus?.current ?? focusable()[0];
    if (initial) {
      initial.focus();
    } else {
      node.tabIndex = -1;
      node.focus();
    }

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && optsRef.current.onEscape) {
        e.preventDefault();
        optsRef.current.onEscape();
        return;
      }
      if (e.key !== "Tab") return;
      const items = focusable();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !node.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last || !node.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      previouslyFocused?.focus?.();
    };
  }, [open, ref]);
}
