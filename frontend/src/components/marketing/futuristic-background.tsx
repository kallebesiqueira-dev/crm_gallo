"use client";

/**
 * Page-wide futuristic background — static. Sits behind every section of
 * the landing, pinned with `fixed inset-0 z-0` so it doesn't scroll with
 * the document and doesn't compete with content. Nothing animates: the
 * mesh, conic spotlight, and grid are baked in and stay perfectly still
 * as the user scrolls.
 *
 * Layers (bottom → top):
 *   1. Base — near-black radial wash so the colour layers bleed naturally.
 *   2. Aurora blobs — three large radial gradients (blue / violet /
 *      fuchsia) frozen in place. They give the mesh its character without
 *      drifting under the eye.
 *   3. Conic spotlight — a very-low-opacity rotated gradient, also frozen,
 *      that adds a sense of depth without committing to one light source.
 *   4. Grid — faint dotted line floor that anchors the perspective. Fixed
 *      offset, no panning.
 *   5. Vignette — soft top/bottom darkening so the hero headline stays
 *      legible at peak brightness.
 *
 * Pointer-events disabled throughout, so it never intercepts anything.
 */
export function FuturisticBackground() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
    >
      {/* 1. Base wash */}
      <div className="absolute inset-0 bg-[radial-gradient(120%_120%_at_50%_0%,#0b1020_0%,#05060d_60%,#040509_100%)]" />

      {/* 2. Frozen aurora blobs */}
      <div className="absolute -left-[15%] top-[5%] h-[55rem] w-[55rem] rounded-full bg-[radial-gradient(closest-side,rgba(59,130,246,0.55),rgba(59,130,246,0)_70%)] blur-3xl opacity-70" />
      <div className="absolute -right-[20%] top-[25%] h-[60rem] w-[60rem] rounded-full bg-[radial-gradient(closest-side,rgba(139,92,246,0.5),rgba(139,92,246,0)_70%)] blur-3xl opacity-70" />
      <div className="absolute bottom-[-20%] left-[20%] h-[55rem] w-[55rem] rounded-full bg-[radial-gradient(closest-side,rgba(217,70,239,0.4),rgba(217,70,239,0)_70%)] blur-3xl opacity-60" />

      {/* 3. Frozen conic spotlight */}
      <div className="absolute left-1/2 top-1/2 h-[120vmax] w-[120vmax] -translate-x-1/2 -translate-y-1/2 opacity-[0.07] [background:conic-gradient(from_0deg_at_50%_50%,transparent,rgba(99,102,241,0.7),transparent_30%,rgba(217,70,239,0.5),transparent_70%,rgba(59,130,246,0.6),transparent)]" />

      {/* 4. Static grid floor */}
      <div className="absolute inset-[-10%] opacity-[0.08] [background-image:linear-gradient(rgba(255,255,255,0.6)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.6)_1px,transparent_1px)] [background-size:72px_72px]" />

      {/* 5. Vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(120%_60%_at_50%_50%,transparent_55%,rgba(0,0,0,0.55)_100%)]" />
    </div>
  );
}
