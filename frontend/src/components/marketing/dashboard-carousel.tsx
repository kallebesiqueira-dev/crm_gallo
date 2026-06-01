"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { AnimatePresence, motion } from "framer-motion";
import {
  BarChart3,
  Calendar,
  CheckCircle2,
  FileText,
  LayoutDashboard,
  MessagesSquare,
  Pause,
  Play,
  Sparkles,
  Target,
  TrendingUp,
  Users,
  Workflow,
} from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Auto-rotating product showcase — five distinct screens of CRM Gallo
 * alternating between dark and light themes. The whole thing is wrapped
 * in a single browser chrome so the swap feels like a real demo, not a
 * collage. Default cadence is 5s/slide; hovering pauses, the user can
 * also step manually via the dots underneath.
 *
 * Each scene is self-contained — same browser frame, different inner
 * payload. They share `themeClass()` so any future theme-aware tweak
 * lands in one place.
 */

type Theme = "dark" | "light";
const SLIDE_DURATION_MS = 5000;

interface Scene {
  id: string;
  theme: Theme;
  url: string;
  title: string;
  render: () => React.ReactNode;
}

const SCENES: Scene[] = [
  { id: "dashboard", theme: "dark",  url: "app.crm-gallo.com/dashboard", title: "Dashboard",     render: () => <DashboardScene theme="dark" /> },
  { id: "leads",     theme: "light", url: "app.crm-gallo.com/leads",     title: "Leads",         render: () => <LeadsScene theme="light" /> },
  { id: "pipeline",  theme: "dark",  url: "app.crm-gallo.com/pipeline",  title: "Pipeline",      render: () => <PipelineScene theme="dark" /> },
  { id: "reports",   theme: "light", url: "app.crm-gallo.com/reports",   title: "Reports",       render: () => <ReportsScene theme="light" /> },
  { id: "assistant", theme: "dark",  url: "app.crm-gallo.com/assistant", title: "AI Assistant",  render: () => <AssistantScene theme="dark" /> },
];

export function DashboardCarousel({ className }: { className?: string }) {
  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);

  // Auto-advance. The interval is owned by the `paused` lifecycle —
  // once started it advances forever via the functional setState. No
  // need to re-arm on every index change, which would reset the 5 s
  // timer mid-flight and burn a cleanup cycle per slide.
  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => {
      setIdx((i) => (i + 1) % SCENES.length);
    }, SLIDE_DURATION_MS);
    return () => clearInterval(t);
  }, [paused]);

  const scene = SCENES[idx];

  return (
    <div className={cn("relative w-full", className)}>
      {/* Frame */}
      <div
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        className="relative w-full overflow-hidden rounded-xl border border-white/10 shadow-2xl shadow-blue-500/20"
      >
        {/* Browser chrome — locked to dark surface so the transition between
            light and dark scenes reads as "switching tabs", not "the whole
            screen flips". */}
        <div className="flex items-center gap-3 border-b border-white/10 bg-slate-900/90 px-4 py-3 backdrop-blur">
          <div className="flex gap-1.5">
            <div className="h-2.5 w-2.5 rounded-full bg-red-400/80" />
            <div className="h-2.5 w-2.5 rounded-full bg-amber-400/80" />
            <div className="h-2.5 w-2.5 rounded-full bg-emerald-400/80" />
          </div>
          <div className="flex flex-1 items-center gap-2 rounded-md bg-slate-800/70 px-3 py-1 text-[10px] text-slate-400">
            <span className="grid h-3.5 w-3.5 place-items-center rounded-full bg-emerald-500/20 text-emerald-400">
              <Sparkles className="h-2 w-2" />
            </span>
            <AnimatePresence mode="wait" initial={false}>
              <motion.span
                key={scene.url}
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                transition={{ duration: 0.25 }}
              >
                {scene.url}
              </motion.span>
            </AnimatePresence>
          </div>
          <div className="hidden items-center gap-1.5 sm:flex">
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-emerald-300">
              Live
            </span>
          </div>
        </div>

        {/* Scene area — explicit min-height so swaps don't pop the layout */}
        <div className="relative min-h-[460px] sm:min-h-[500px]">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={scene.id}
              initial={{ opacity: 0, scale: 0.98, filter: "blur(10px)" }}
              animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
              exit={{ opacity: 0, scale: 1.01, filter: "blur(10px)" }}
              transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
              className="absolute inset-0"
            >
              {scene.render()}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Progress bar across the bottom of the frame */}
        <div className="absolute inset-x-0 bottom-0 h-0.5 bg-white/5">
          <motion.div
            key={`${scene.id}-${paused}`}
            initial={{ width: "0%" }}
            animate={{ width: paused ? "0%" : "100%" }}
            transition={{ duration: paused ? 0 : SLIDE_DURATION_MS / 1000, ease: "linear" }}
            className="h-full bg-gradient-to-r from-blue-400 via-violet-400 to-fuchsia-400"
          />
        </div>
      </div>

      {/* Controls — dots + scene label + play/pause */}
      <div className="mt-5 flex items-center justify-center gap-4">
        <button
          type="button"
          onClick={() => setPaused((p) => !p)}
          aria-label={paused ? "Play" : "Pause"}
          className="grid h-7 w-7 place-items-center rounded-full border border-white/10 bg-white/5 text-muted-foreground transition-all hover:scale-110 hover:border-white/30 hover:text-foreground"
        >
          {paused ? <Play className="h-3 w-3" /> : <Pause className="h-3 w-3" />}
        </button>

        <div className="flex items-center gap-2">
          {SCENES.map((s, i) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setIdx(i)}
              aria-label={s.title}
              className={cn(
                "h-1.5 rounded-full transition-all duration-300",
                i === idx
                  ? "w-8 bg-foreground"
                  : "w-1.5 bg-foreground/25 hover:bg-foreground/50",
              )}
            />
          ))}
        </div>

        <div className="w-20 text-xs text-muted-foreground tabular-nums">
          {String(idx + 1).padStart(2, "0")} / {String(SCENES.length).padStart(2, "0")}
        </div>
      </div>
    </div>
  );
}

/* ────────────────────────── Theme palette helper ────────────────────────── */

function themeClass(theme: Theme, dark: string, light: string) {
  return theme === "dark" ? dark : light;
}

function SceneShell({ theme, children }: { theme: Theme; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "flex min-h-[460px] sm:min-h-[500px]",
        themeClass(theme, "bg-slate-950 text-slate-100", "bg-slate-50 text-slate-900"),
      )}
    >
      <Sidebar theme={theme} />
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}

/* ─────────────────────────────── Sidebar ────────────────────────────────── */

const NAV = [
  { icon: LayoutDashboard, label: "Dashboard" },
  { icon: Target,          label: "Leads", badge: 12 },
  { icon: Users,           label: "Customers" },
  { icon: Workflow,        label: "Pipeline" },
  { icon: MessagesSquare,  label: "Tasks" },
  { icon: Calendar,        label: "Calendar" },
  { icon: FileText,        label: "Documents" },
  { icon: Sparkles,        label: "AI Assistant" },
  { icon: BarChart3,       label: "Reports" },
];

function Sidebar({ theme }: { theme: Theme }) {
  // Active item picked from the URL so the sidebar visually mirrors the
  // scene the user is on. We infer it by scanning for a label match —
  // small detail, but it sells the "real product" feel.
  return (
    <aside
      className={cn(
        "hidden w-44 shrink-0 border-r p-3 md:block",
        themeClass(
          theme,
          "border-white/5 bg-slate-900/60",
          "border-slate-200 bg-white",
        ),
      )}
    >
      <div className="mb-4 flex items-center gap-2 px-2">
        <Image
          src="/logo.png"
          alt=""
          width={28}
          height={28}
          className="h-7 w-7 shrink-0 rounded-full select-none"
        />
        <div className="min-w-0">
          <div
            className={cn(
              "bg-gradient-to-r bg-clip-text text-[12px] font-bold leading-tight tracking-tight text-transparent",
              themeClass(theme, "from-white via-white to-blue-200", "from-slate-900 via-slate-900 to-blue-600"),
            )}
          >
            CRM Gallo
          </div>
          <div
            className={cn(
              "text-[9px] font-medium uppercase tracking-[0.08em]",
              themeClass(theme, "text-slate-500", "text-slate-400"),
            )}
          >
            AI Sales Platform
          </div>
        </div>
      </div>

      <nav className="space-y-0.5">
        {NAV.map((item) => (
          <div
            key={item.label}
            className={cn(
              "flex items-center gap-2 rounded-md px-2 py-1.5 text-[11px] transition-colors",
              themeClass(theme, "text-slate-400 hover:bg-white/5", "text-slate-600 hover:bg-slate-100"),
            )}
          >
            <item.icon className="h-3 w-3" />
            <span className="flex-1">{item.label}</span>
            {item.badge && (
              <span
                className={cn(
                  "rounded-full px-1.5 py-0.5 text-[8px] font-semibold",
                  themeClass(theme, "bg-blue-500/20 text-blue-300", "bg-blue-100 text-blue-700"),
                )}
              >
                {item.badge}
              </span>
            )}
          </div>
        ))}
      </nav>
    </aside>
  );
}

/* ─────────────────────────────── Scenes ─────────────────────────────────── */

function PageHeader({
  theme,
  greeting,
  title,
  rightTag,
}: {
  theme: Theme;
  greeting: string;
  title: string;
  rightTag?: string;
}) {
  return (
    <header className="flex items-center justify-between border-b border-white/5 px-5 py-4">
      <div>
        <div className={cn("text-xs", themeClass(theme, "text-slate-400", "text-slate-500"))}>
          {greeting}
        </div>
        <div className={cn("text-base font-semibold", themeClass(theme, "text-white", "text-slate-900"))}>
          {title}
        </div>
      </div>
      <div className="flex items-center gap-2">
        {rightTag && (
          <span
            className={cn(
              "rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wider",
              themeClass(
                theme,
                "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
                "border-emerald-200 bg-emerald-50 text-emerald-700",
              ),
            )}
          >
            {rightTag}
          </span>
        )}
        <div className="h-7 w-7 rounded-full bg-gradient-to-br from-pink-400 to-rose-500" />
      </div>
    </header>
  );
}

/* Scene 1 — Dashboard (dark) */
function DashboardScene({ theme }: { theme: Theme }) {
  const KPIS = [
    { label: "Total leads",     value: "2,847", delta: "+12.4%", tone: "emerald" },
    { label: "Pipeline value",  value: "€421k", delta: "+8.1%",  tone: "blue" },
    { label: "Conversion",      value: "24.3%", delta: "+2.1%",  tone: "violet" },
    { label: "Open tasks",      value: "47",    delta: "-5",     tone: "amber" },
  ];
  const STAGES = [
    { label: "New",         value: 28, color: "from-indigo-500 to-indigo-400" },
    { label: "Contacted",   value: 42, color: "from-cyan-500 to-cyan-400" },
    { label: "Qualified",   value: 31, color: "from-teal-500 to-teal-400" },
    { label: "Proposal",    value: 18, color: "from-amber-500 to-amber-400" },
    { label: "Negotiation", value: 12, color: "from-orange-500 to-orange-400" },
    { label: "Won",         value: 9,  color: "from-emerald-500 to-emerald-400" },
  ];
  const maxStage = Math.max(...STAGES.map((s) => s.value));

  return (
    <SceneShell theme={theme}>
      <PageHeader theme={theme} greeting="Welcome back, Sofia" title="Sales Overview" rightTag="Premium" />
      <div className="space-y-4 p-5">
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          {KPIS.map((k) => (
            <div key={k.label} className="relative overflow-hidden rounded-lg border border-white/5 bg-slate-900/60 p-3">
              <div className="text-[9px] uppercase tracking-wider text-slate-400">{k.label}</div>
              <div className="mt-0.5 text-lg font-semibold text-white">{k.value}</div>
              <div className={cn("mt-0.5 inline-flex items-center gap-1 text-[10px] font-medium", k.tone === "amber" ? "text-amber-400" : "text-emerald-400")}>
                <TrendingUp className="h-2.5 w-2.5" /> {k.delta}
              </div>
            </div>
          ))}
        </div>

        <div className="grid gap-3 lg:grid-cols-5">
          <div className="rounded-lg border border-white/5 bg-slate-900/40 p-3 lg:col-span-3">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Leads by stage</div>
              <div className="text-[9px] text-slate-500">Last 30 days</div>
            </div>
            <div className="flex h-32 items-end gap-2">
              {STAGES.map((s) => (
                <div key={s.label} className="flex flex-1 flex-col items-center gap-1">
                  <div className="text-[10px] font-semibold text-white">{s.value}</div>
                  <div
                    className={cn("w-full rounded-t-md bg-gradient-to-t", s.color)}
                    style={{ height: `${(s.value / maxStage) * 80}px` }}
                  />
                  <div className="truncate text-[9px] text-slate-500">{s.label}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-lg border border-white/5 bg-slate-900/40 p-3 lg:col-span-2">
            <div className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Top leads · AI score</div>
            <div className="space-y-2">
              {[
                { name: "Sofia Martins", company: "Northwind GmbH", score: 87, color: "bg-emerald-500" },
                { name: "Lucas Pereira", company: "Acme Industries", score: 72, color: "bg-amber-500" },
                { name: "Anna Schmidt",  company: "Globex SA",      score: 64, color: "bg-blue-500" },
                { name: "Pedro Álvarez", company: "Initech SL",     score: 81, color: "bg-emerald-500" },
              ].map((l) => (
                <div key={l.name} className="flex items-center gap-2 rounded-md bg-slate-950/50 px-2 py-1.5">
                  <div className={cn("h-6 w-6 shrink-0 rounded-full", l.color)} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[10px] font-medium text-white">{l.name}</div>
                    <div className="truncate text-[9px] text-slate-400">{l.company}</div>
                  </div>
                  <div className="text-[10px] font-semibold text-white">{l.score}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-2">
          <div className="flex items-center gap-2">
            <div className="grid h-7 w-7 place-items-center rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white">
              <Sparkles className="h-3 w-3" />
            </div>
            <div>
              <div className="text-[10px] font-semibold text-white">AI suggests: Follow up with Sofia Martins</div>
              <div className="text-[9px] text-slate-400">Score jumped from 72 → 87 after the product demo. Send the pricing proposal today.</div>
            </div>
          </div>
        </div>
      </div>
    </SceneShell>
  );
}

/* Scene 2 — Leads list (light) */
function LeadsScene({ theme }: { theme: Theme }) {
  const LEADS = [
    { name: "Sofia Martins",  company: "Northwind GmbH",   stage: "Qualified",   score: 87, owner: "Andrea M.", color: "bg-emerald-500" },
    { name: "Lucas Pereira",  company: "Acme Industries",  stage: "Proposal",    score: 72, owner: "Andrea M.", color: "bg-amber-500" },
    { name: "Anna Schmidt",   company: "Globex SA",        stage: "Contacted",   score: 64, owner: "Lea P.",    color: "bg-blue-500" },
    { name: "Pedro Álvarez",  company: "Initech SL",       stage: "Qualified",   score: 81, owner: "Lea P.",    color: "bg-emerald-500" },
    { name: "James Wilson",   company: "Hooli",            stage: "Negotiation", score: 92, owner: "Joana R.",  color: "bg-violet-500" },
    { name: "Marta Rosso",    company: "Vandelay Co.",     stage: "New",         score: 45, owner: "Andrea M.", color: "bg-slate-500" },
    { name: "Carlos Ruiz",    company: "Stark Industries", stage: "Contacted",   score: 58, owner: "Lea P.",    color: "bg-blue-500" },
  ];

  const STAGE_TONE: Record<string, string> = {
    New:         "bg-slate-100  text-slate-700",
    Contacted:   "bg-blue-100   text-blue-700",
    Qualified:   "bg-emerald-100 text-emerald-700",
    Proposal:    "bg-amber-100  text-amber-700",
    Negotiation: "bg-violet-100 text-violet-700",
  };

  return (
    <SceneShell theme={theme}>
      <PageHeader theme={theme} greeting="2,847 leads · 12 added today" title="Leads" rightTag="Premium" />
      <div className="space-y-3 p-5">
        <div className="flex items-center gap-2">
          <div className="flex flex-1 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px] text-slate-500">
            <Sparkles className="h-3 w-3 text-blue-500" />
            Search by name, email, company…
          </div>
          <div className="rounded-md bg-blue-600 px-3 py-1.5 text-[11px] font-semibold text-white shadow-sm">+ New lead</div>
        </div>

        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <div className="grid grid-cols-12 gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2 text-[9px] font-semibold uppercase tracking-wider text-slate-500">
            <div className="col-span-4">Name</div>
            <div className="col-span-3">Company</div>
            <div className="col-span-2">Stage</div>
            <div className="col-span-2">AI Score</div>
            <div className="col-span-1">Owner</div>
          </div>
          {LEADS.map((l) => (
            <div key={l.name} className="grid grid-cols-12 items-center gap-2 border-b border-slate-100 px-3 py-2 last:border-0 hover:bg-slate-50">
              <div className="col-span-4 flex items-center gap-2 text-[11px] font-medium text-slate-900">
                <div className={cn("grid h-6 w-6 shrink-0 place-items-center rounded-full text-[9px] font-bold text-white", l.color)}>
                  {l.name.split(" ").map((p) => p[0]).join("").slice(0, 2)}
                </div>
                {l.name}
              </div>
              <div className="col-span-3 text-[11px] text-slate-600">{l.company}</div>
              <div className="col-span-2">
                <span className={cn("rounded-full px-2 py-0.5 text-[9px] font-semibold", STAGE_TONE[l.stage] ?? "bg-slate-100 text-slate-700")}>
                  {l.stage}
                </span>
              </div>
              <div className="col-span-2 flex items-center gap-2">
                <div className="h-1.5 w-12 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={cn("h-full rounded-full", l.score >= 80 ? "bg-emerald-500" : l.score >= 60 ? "bg-amber-500" : "bg-slate-400")}
                    style={{ width: `${l.score}%` }}
                  />
                </div>
                <span className="text-[10px] font-semibold text-slate-900">{l.score}</span>
              </div>
              <div className="col-span-1 text-[10px] text-slate-500">{l.owner}</div>
            </div>
          ))}
        </div>
      </div>
    </SceneShell>
  );
}

/* Scene 3 — Pipeline (dark) */
function PipelineScene({ theme }: { theme: Theme }) {
  const COLUMNS = [
    { label: "New",          count: 12, color: "bg-indigo-500/20 text-indigo-300",   cards: [
      { title: "Acme — Annual Plan", value: "€18,400", prob: 35 },
      { title: "Globex — Pilot",     value: "€6,200",  prob: 25 },
    ]},
    { label: "Qualified",    count: 8,  color: "bg-teal-500/20 text-teal-300",       cards: [
      { title: "Northwind — Renewal", value: "€42,000", prob: 60 },
      { title: "Wayne — Expansion",   value: "€28,500", prob: 55 },
    ]},
    { label: "Proposal",     count: 5,  color: "bg-amber-500/20 text-amber-300",     cards: [
      { title: "Stark — Premium",     value: "€56,000", prob: 70, highlight: true },
    ]},
    { label: "Negotiation",  count: 3,  color: "bg-orange-500/20 text-orange-300",   cards: [
      { title: "Hooli — Enterprise",  value: "€124,000", prob: 85 },
    ]},
    { label: "Won",          count: 9,  color: "bg-emerald-500/20 text-emerald-300", cards: [
      { title: "Tyrell — 12-month",   value: "€72,000", prob: 100 },
    ]},
  ];

  return (
    <SceneShell theme={theme}>
      <PageHeader theme={theme} greeting="€724,100 weighted · 37 deals" title="Pipeline" rightTag="Premium" />
      <div className="p-5">
        <div className="grid grid-cols-5 gap-2">
          {COLUMNS.map((c) => (
            <div key={c.label} className="space-y-2">
              <div className="flex items-center justify-between rounded-md bg-slate-900/60 px-2 py-1.5">
                <span className={cn("rounded px-1.5 py-0.5 text-[9px] font-semibold", c.color)}>{c.label}</span>
                <span className="text-[9px] text-slate-400">{c.count}</span>
              </div>
              <div className="space-y-1.5">
                {c.cards.map((d, i) => (
                  <div
                    key={i}
                    className={cn(
                      "rounded-md border border-white/5 bg-slate-900/80 p-2",
                      d.highlight && "rotate-[1.5deg] shadow-lg ring-2 ring-violet-500/40",
                    )}
                  >
                    <div className="truncate text-[10px] font-medium text-white">{d.title}</div>
                    <div className="mt-1 flex items-center justify-between text-[9px]">
                      <span className="font-mono text-slate-300">{d.value}</span>
                      <span className="text-slate-500">{d.prob}%</span>
                    </div>
                    <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-slate-800">
                      <div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500" style={{ width: `${d.prob}%` }} />
                    </div>
                  </div>
                ))}
                <div className="rounded-md border border-dashed border-white/10 py-1.5 text-center text-[9px] text-slate-500">+ Add deal</div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 flex items-center gap-2 rounded-md border border-blue-500/30 bg-blue-500/10 p-2 text-[10px] text-slate-300">
          <Target className="h-3 w-3 text-blue-400" />
          Forecast this month: <span className="font-mono text-white">€186,500</span> closing weighted by AI probability.
        </div>
      </div>
    </SceneShell>
  );
}

/* Scene 4 — Reports (light) */
function ReportsScene({ theme }: { theme: Theme }) {
  const MONTHLY = [38, 52, 47, 61, 73, 68, 82, 91, 84, 97, 105, 118];
  const max = Math.max(...MONTHLY);
  const FUNNEL = [
    { label: "Leads",      value: 2847, pct: 100, color: "bg-blue-500" },
    { label: "Qualified",  value: 1620, pct: 57,  color: "bg-violet-500" },
    { label: "Proposals",  value: 740,  pct: 26,  color: "bg-fuchsia-500" },
    { label: "Won",        value: 312,  pct: 11,  color: "bg-emerald-500" },
  ];

  return (
    <SceneShell theme={theme}>
      <PageHeader theme={theme} greeting="Last 12 months · auto-refreshed" title="Reports" rightTag="Premium" />
      <div className="grid gap-3 p-5 lg:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-white p-3 lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Leads created · monthly</div>
            <div className="text-[10px] font-semibold text-emerald-600">↑ 2.4× YoY</div>
          </div>
          <div className="flex h-40 items-end gap-1.5">
            {MONTHLY.map((v, i) => (
              <div key={i} className="flex flex-1 flex-col items-center gap-1">
                <div className="w-full rounded-t-md bg-gradient-to-t from-blue-600 to-violet-500" style={{ height: `${(v / max) * 100}%` }} />
                <div className="text-[8px] text-slate-400">{["J","F","M","A","M","J","J","A","S","O","N","D"][i]}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-3">
          <div className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Conversion</div>
          <div className="relative mx-auto grid h-32 w-32 place-items-center">
            <svg viewBox="0 0 36 36" className="absolute inset-0 -rotate-90">
              <circle cx="18" cy="18" r="15.9155" fill="none" stroke="#e2e8f0" strokeWidth="3" />
              <circle cx="18" cy="18" r="15.9155" fill="none" stroke="url(#donut)" strokeWidth="3" strokeDasharray="24.3 100" strokeLinecap="round" />
              <defs>
                <linearGradient id="donut">
                  <stop offset="0%" stopColor="#3b82f6" />
                  <stop offset="100%" stopColor="#a855f7" />
                </linearGradient>
              </defs>
            </svg>
            <div className="text-center">
              <div className="text-2xl font-bold text-slate-900">24.3%</div>
              <div className="text-[9px] text-slate-500">closed/won</div>
            </div>
          </div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-3 lg:col-span-3">
          <div className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Sales funnel</div>
          <div className="space-y-1.5">
            {FUNNEL.map((f) => (
              <div key={f.label} className="flex items-center gap-3 text-[10px]">
                <div className="w-20 text-slate-700">{f.label}</div>
                <div className="flex-1 overflow-hidden rounded-full bg-slate-100">
                  <div className={cn("h-4 rounded-full", f.color)} style={{ width: `${f.pct}%` }} />
                </div>
                <div className="w-20 text-right tabular-nums text-slate-700">{f.value.toLocaleString()}</div>
                <div className="w-10 text-right text-slate-500">{f.pct}%</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </SceneShell>
  );
}

/* Scene 5 — AI Assistant (dark) */
function AssistantScene({ theme }: { theme: Theme }) {
  return (
    <SceneShell theme={theme}>
      <PageHeader theme={theme} greeting="Claude Sonnet · grounded on your CRM" title="AI Assistant" rightTag="Premium" />
      <div className="grid gap-3 p-5 lg:grid-cols-3">
        {/* Conversation */}
        <div className="space-y-3 rounded-lg border border-white/5 bg-slate-900/40 p-3 lg:col-span-2">
          <Bubble side="left">
            Which leads should I prioritise this week?
          </Bubble>
          <Bubble side="right" ai>
            Looking at your pipeline, I&rsquo;d focus on <strong>three</strong> deals before Friday:
            <ul className="mt-2 space-y-1.5">
              {[
                { name: "Sofia Martins", reason: "Score jumped 72 → 87 after the demo. Send pricing today." },
                { name: "James Wilson",  reason: "Negotiation stalled 11 days. Re-engage with case study." },
                { name: "Pedro Álvarez", reason: "Open task overdue: contract clauses. 2 min reply." },
              ].map((s) => (
                <li key={s.name} className="flex items-start gap-2 rounded-md bg-slate-950/60 px-2 py-1.5">
                  <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-emerald-400" />
                  <div className="text-[10px]">
                    <div className="font-semibold text-white">{s.name}</div>
                    <div className="text-slate-400">{s.reason}</div>
                  </div>
                </li>
              ))}
            </ul>
          </Bubble>
          <Bubble side="left">Draft the email for Sofia in Italian.</Bubble>
          <Bubble side="right" ai typing />
        </div>

        {/* Context panel */}
        <div className="rounded-lg border border-white/5 bg-slate-900/40 p-3">
          <div className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Context</div>
          <div className="space-y-2 text-[10px]">
            <Ctx label="Active lead"     value="Sofia Martins · Northwind GmbH" />
            <Ctx label="AI score"        value="87 / 100" tone="emerald" />
            <Ctx label="Last activity"   value="Product demo · 2 days ago" />
            <Ctx label="Next action"     value="Send pricing proposal" tone="violet" />
            <Ctx label="Language"        value="🇮🇹 Italiano" />
          </div>
          <div className="mt-3 rounded-md bg-violet-500/10 px-2 py-1.5 text-[10px] text-violet-300">
            <Sparkles className="mr-1 inline h-2.5 w-2.5" />
            +37% reply rate when drafted in the lead&rsquo;s preferred language.
          </div>
        </div>
      </div>
    </SceneShell>
  );
}

function Bubble({
  side,
  ai,
  typing,
  children,
}: {
  side: "left" | "right";
  ai?: boolean;
  typing?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className={cn("flex items-start gap-2", side === "right" && "flex-row-reverse")}>
      <div
        className={cn(
          "h-6 w-6 shrink-0 rounded-full",
          ai ? "grid place-items-center bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white" : "bg-gradient-to-br from-pink-400 to-rose-500",
        )}
      >
        {ai && <Sparkles className="h-3 w-3" />}
      </div>
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-3 py-2 text-[10px] leading-relaxed",
          ai ? "bg-violet-500/10 text-slate-200" : "bg-slate-800 text-slate-300",
          side === "right" ? "rounded-tr-sm" : "rounded-tl-sm",
        )}
      >
        {typing ? (
          <span className="inline-flex items-center gap-1">
            <Dot delay="0s" /> <Dot delay="0.15s" /> <Dot delay="0.3s" />
          </span>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-violet-400"
      style={{ animationDelay: delay }}
    />
  );
}

function Ctx({ label, value, tone }: { label: string; value: string; tone?: "emerald" | "violet" }) {
  return (
    <div className="flex items-center justify-between rounded-md bg-slate-950/40 px-2 py-1.5">
      <span className="text-slate-500">{label}</span>
      <span
        className={cn(
          "font-medium",
          tone === "emerald" && "text-emerald-300",
          tone === "violet" && "text-violet-300",
          !tone && "text-slate-200",
        )}
      >
        {value}
      </span>
    </div>
  );
}
