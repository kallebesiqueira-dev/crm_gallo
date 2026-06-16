"use client";

import { Lock } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Landing showcase — a real screen recording of the GALLO CRM dashboard,
 * wrapped in the same browser chrome the old carousel used so the section
 * keeps its "this is the live product" feel.
 *
 * SWAP THE VIDEO: drop a new file in `public/` — no code change needed:
 *   • public/demo_video.mp4   (H.264, web-optimized + faststart)
 * This component is the single source of truth for the showcase video, so a
 * future narrated/edited cut just replaces that file.
 */
const VIDEO_MP4 = "/demo_video.mp4";

export function DashboardVideo({ className }: { className?: string }) {
  return (
    <div className={cn("relative w-full", className)}>
      {/* Framed, glass-bordered showcase for the product tour video. */}
      <div className="relative w-full overflow-hidden rounded-xl border border-white/10 shadow-2xl shadow-blue-500/20">
        {/* Browser chrome */}
        <div className="flex items-center gap-3 border-b border-white/10 bg-slate-900/90 px-4 py-3 backdrop-blur">
          <div className="flex gap-1.5">
            <div className="h-2.5 w-2.5 rounded-full bg-red-400/80" />
            <div className="h-2.5 w-2.5 rounded-full bg-amber-400/80" />
            <div className="h-2.5 w-2.5 rounded-full bg-emerald-400/80" />
          </div>
          <div className="flex flex-1 items-center gap-2 rounded-md bg-slate-800/70 px-3 py-1 text-[10px] text-slate-400">
            <span className="grid h-3.5 w-3.5 place-items-center rounded-full bg-emerald-500/20 text-emerald-400">
              <Lock className="h-2 w-2" />
            </span>
            app.gallo-crm.com/dashboard
          </div>
        </div>

        {/* Recording. Muted autoplay + loop keeps the section alive; controls
            let visitors replay, scrub, or unmute. Aspect matches the source
            (1334×600) so the full frame shows without cropping. */}
        <video
          className="block aspect-[1334/600] w-full bg-slate-950 object-cover"
          autoPlay
          muted
          loop
          playsInline
          controls
          preload="metadata"
          aria-label="GALLO CRM dashboard product tour"
        >
          <source src={VIDEO_MP4} type="video/mp4" />
        </video>
      </div>
    </div>
  );
}
