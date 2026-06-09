"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useLocale } from "next-intl";
import {
  ArrowUpRight,
  Bell,
  Building2,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  FileText,
  Mail,
  Phone,
  Settings2,
  Target,
  TrendingUp,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type DashboardStats } from "@/lib/api";
import { getToken } from "@/lib/auth";

/**
 * GALLO CRM — premium dashboard.
 *
 * Light: white cards on a soft tinted background, purple accents.
 * Dark: landing-style purple/black gradient + glassmorphism cards.
 *
 * KPI cards + the pipeline funnel read real stats from `api.stats` where the
 * value exists; the remaining widgets show representative data until their
 * back-ends land (citazioni, communications, documents) — all i18n is a
 * fast-follow, labels are currently Italian to match the reference design.
 */
export default function DashboardPage() {
  const locale = useLocale();
  const [stats, setStats] = useState<DashboardStats | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.stats(token).then(setStats).catch(() => setStats(null));
  }, []);

  const eur = useMemo(
    () => new Intl.NumberFormat(locale, { style: "currency", currency: "EUR", maximumFractionDigits: 0 }),
    [locale],
  );
  const eur2 = useMemo(
    () => new Intl.NumberFormat(locale, { style: "currency", currency: "EUR", minimumFractionDigits: 2 }),
    [locale],
  );
  const int = useMemo(() => new Intl.NumberFormat(locale), [locale]);

  const kpis = [
    { label: "Lead totali", value: stats ? int.format(stats.total_leads) : "1.250", delta: "+12.5%", up: true, icon: Users },
    { label: "Opportunità", value: stats ? int.format(stats.total_deals) : "320", delta: "+8.2%", up: true, icon: Target },
    { label: "Fatturato (Mese)", value: stats ? eur.format(stats.pipeline_value_eur || 0) : "€ 125.430", delta: "+15.3%", up: true, icon: TrendingUp },
    { label: "Attività completate", value: "85%", delta: "+6.1%", up: true, icon: CheckCircle2 },
  ];

  return (
    <div className="relative space-y-5">
      {/* Dark-mode ambient (landing-style) — light mode keeps the soft bg */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 -z-10 hidden dark:block bg-[radial-gradient(120%_120%_at_15%_0%,#1a1033_0%,#0d0a18_55%,#080611_100%)]"
      >
        <div className="absolute -left-[10%] top-[8%] h-[40rem] w-[40rem] rounded-full bg-[radial-gradient(closest-side,rgba(139,92,246,0.22),transparent_70%)] blur-3xl" />
        <div className="absolute -right-[12%] bottom-[0%] h-[40rem] w-[40rem] rounded-full bg-[radial-gradient(closest-side,rgba(217,70,239,0.16),transparent_70%)] blur-3xl" />
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <button className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium text-foreground shadow-sm transition hover:border-primary/40">
          <CalendarDays className="h-4 w-4 text-primary" />
          01 Mag 2025 – 31 Mag 2025
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </button>
        <button className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium text-foreground shadow-sm transition hover:border-primary/40">
          <Settings2 className="h-4 w-4 text-primary" />
          Personalizza
        </button>
      </div>

      {/* KPI row */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map((k) => (
          <Panel key={k.label} className="p-5">
            <div className="flex items-start justify-between">
              <div className="text-sm font-medium text-muted-foreground">{k.label}</div>
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary">
                <k.icon className="h-5 w-5" />
              </span>
            </div>
            <div className="mt-3 flex items-end gap-2">
              <div className="text-3xl font-bold tracking-tight">{k.value}</div>
              <span className={cn("mb-1 text-xs font-semibold", k.up ? "text-emerald-500" : "text-rose-500")}>
                {k.delta}
              </span>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">vs periodo precedente</div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-primary/10">
              <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-500" style={{ width: "72%" }} />
            </div>
          </Panel>
        ))}
      </div>

      {/* Finance + citazioni */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel className="p-5 lg:col-span-2">
          <div className="flex items-center justify-between">
            <SectionTitle icon={TrendingUp}>Panoramica finanziaria</SectionTitle>
            <div className="flex items-center gap-2 text-xs font-medium">
              <span className="text-primary">Ricavi</span>
              <span className="relative h-5 w-9 rounded-full bg-primary/30">
                <span className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-primary" />
              </span>
              <span className="text-muted-foreground">Spese</span>
            </div>
          </div>
          <div className="mt-4 grid gap-6 md:grid-cols-[1.4fr_1fr]">
            <div>
              <div className="text-xs text-muted-foreground">Pagamenti</div>
              <div className="text-sm font-semibold">Totale € 125.430,00</div>
              <PaymentsBars />
            </div>
            <div className="border-l border-border pl-5">
              <div className="text-xs text-muted-foreground">Importi aperti</div>
              <DonutOpen pct={26} />
              <div className="mt-3 space-y-1.5 text-xs">
                <LegendRow color="bg-violet-500" label="Aperto" value={eur2.format(46792.2)} />
                <LegendRow color="bg-rose-500" label="In ritardo" value={eur2.format(11802.2)} />
              </div>
            </div>
          </div>
        </Panel>

        <Panel className="p-5">
          <SectionTitle icon={FileText}>Citazioni</SectionTitle>
          <div className="mt-2 text-xs text-muted-foreground">Totale offerto</div>
          <div className="text-lg font-bold">€ 1.250.220,20</div>
          <div className="mt-2 flex items-center gap-4">
            <CitazioniRings />
            <div className="flex-1 space-y-2 text-xs">
              <LegendRow color="bg-violet-500" label="Eccezionale" value={eur2.format(212050.5)} />
              <LegendRow color="bg-fuchsia-500" label="Accettato" value={eur2.format(330050)} />
              <LegendRow color="bg-rose-400" label="Rifiutato" value={eur2.format(158020.2)} />
            </div>
          </div>
        </Panel>
      </div>

      {/* Activities + pipeline + my tasks */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel className="flex flex-col p-5">
          <SectionTitle icon={CheckCircle2}>Attività recenti</SectionTitle>
          <div className="mt-3 space-y-1">
            {RECENT_ACTIVITIES.map((a) => (
              <div key={a.title} className="flex items-center gap-3 rounded-lg px-2 py-2 transition hover:bg-accent">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                  <a.icon className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{a.title}</div>
                  <div className="truncate text-xs text-muted-foreground">{a.sub}</div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="text-[11px] text-muted-foreground">{a.time}</div>
                  <StatusPill status={a.status} />
                </div>
              </div>
            ))}
          </div>
          <CardLink href={`/${locale}/tasks`}>Vedi tutte le attività</CardLink>
        </Panel>

        <Panel className="flex flex-col p-5">
          <div className="flex items-center justify-between">
            <SectionTitle icon={Target}>Pipeline</SectionTitle>
            <span className="rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground">Tutte le pipeline</span>
          </div>
          <Funnel stats={stats} eur={eur} />
          <CardLink href={`/${locale}/pipeline`}>Vai alla pipeline</CardLink>
        </Panel>

        <Panel className="flex flex-col p-5">
          <div className="flex items-center justify-between">
            <SectionTitle icon={CalendarDays}>Le mie attività</SectionTitle>
            <span className="rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground">Oggi</span>
          </div>
          <div className="mt-3 space-y-1">
            {MY_TASKS.map((m) => (
              <div key={m.title} className="flex items-center gap-3 rounded-lg px-2 py-2 transition hover:bg-accent">
                <span className="h-4 w-4 shrink-0 rounded-full border-2 border-primary/50" />
                <div className="flex-1 truncate text-sm">{m.title}</div>
                <div className="shrink-0 text-xs font-medium text-muted-foreground tabular-nums">{m.time}</div>
              </div>
            ))}
          </div>
          <CardLink href={`/${locale}/calendar`}>Vedi calendario</CardLink>
        </Panel>
      </div>

      {/* Clients + documents */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel className="p-5 lg:col-span-2">
          <div className="flex items-center justify-between">
            <SectionTitle icon={Building2}>Clienti / Partner recenti</SectionTitle>
            <CardLinkInline href={`/${locale}/companies`}>Vedi tutti</CardLinkInline>
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {COMPANIES.map((c) => (
              <div key={c.name} className="rounded-xl border border-border bg-background/40 p-3 transition hover:border-primary/40 hover:shadow-sm">
                <span className={cn("grid h-9 w-9 place-items-center rounded-lg text-sm font-bold text-white", c.color)}>
                  {c.initials}
                </span>
                <div className="mt-2 truncate text-sm font-semibold">{c.name}</div>
                <div className="truncate text-xs text-muted-foreground">{c.kind}</div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel className="p-5">
          <div className="flex items-center justify-between">
            <SectionTitle icon={FileText}>Ultimi documenti</SectionTitle>
            <CardLinkInline href={`/${locale}/documents`}>Vedi tutti</CardLinkInline>
          </div>
          <div className="mt-3 space-y-1">
            {DOCUMENTS.map((d) => (
              <div key={d.name} className="flex items-center gap-3 rounded-lg px-2 py-2 transition hover:bg-accent">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-rose-500/10 text-rose-500">
                  <FileText className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1 truncate text-sm">{d.name}</div>
                <div className="shrink-0 text-[11px] text-muted-foreground">{d.time}</div>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <p className="pt-1 text-center text-[11px] text-muted-foreground/60">
        Anteprima del nuovo design · dati di esempio dove il back-end non è ancora collegato
      </p>
    </div>
  );
}

/* ───────────────────────── primitives ───────────────────────── */

function Panel({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "rounded-2xl border bg-card shadow-sm",
        "border-border",
        "dark:border-white/10 dark:bg-white/[0.04] dark:backdrop-blur-xl dark:shadow-[0_8px_40px_-12px_rgba(139,92,246,0.25)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

function SectionTitle({ icon: Icon, children }: { icon: typeof Target; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-sm font-semibold">
      <Icon className="h-4 w-4 text-primary" />
      {children}
    </div>
  );
}

function LegendRow({ color, label, value }: { color: string; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-2 text-muted-foreground">
        <span className={cn("h-2.5 w-2.5 rounded-full", color)} />
        {label}
      </span>
      <span className="font-semibold text-foreground">{value}</span>
    </div>
  );
}

function StatusPill({ status }: { status: "Completata" | "In attesa" }) {
  return (
    <span
      className={cn(
        "mt-0.5 inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold",
        status === "Completata"
          ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
          : "bg-amber-500/10 text-amber-600 dark:text-amber-400",
      )}
    >
      {status}
    </span>
  );
}

function CardLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="mt-auto block rounded-lg border border-border py-2 text-center text-xs font-semibold text-primary transition hover:bg-primary/5"
    >
      {children}
    </Link>
  );
}

function CardLinkInline({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline">
      {children} <ArrowUpRight className="h-3 w-3" />
    </Link>
  );
}

/* ───────────────────────── charts ───────────────────────── */

const MONTHS = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];
const PAY = [30, 18, 22, 33, 20, 30, 13, 9, 12, 25, 11, 23];

function PaymentsBars() {
  const max = Math.max(...PAY);
  return (
    <div className="mt-3 flex h-36 items-end gap-1.5">
      {PAY.map((v, i) => (
        <div key={i} className="flex flex-1 flex-col items-center gap-1">
          <div
            className="w-full rounded-t-md bg-gradient-to-t from-violet-600 to-fuchsia-400 transition-all hover:opacity-80"
            style={{ height: `${(v / max) * 100}%` }}
          />
          <span className="text-[9px] text-muted-foreground">{MONTHS[i]}</span>
        </div>
      ))}
    </div>
  );
}

function DonutOpen({ pct }: { pct: number }) {
  const r = 42;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative mx-auto mt-3 grid h-32 w-32 place-items-center">
      <svg viewBox="0 0 100 100" className="absolute inset-0 -rotate-90">
        <circle cx="50" cy="50" r={r} fill="none" stroke="currentColor" strokeWidth="12" className="text-primary/10" />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke="url(#donutOpen)"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * c} ${c}`}
        />
        <defs>
          <linearGradient id="donutOpen" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#8b5cf6" />
            <stop offset="100%" stopColor="#d946ef" />
          </linearGradient>
        </defs>
      </svg>
      <div className="text-2xl font-bold text-primary">{pct}%</div>
    </div>
  );
}

function CitazioniRings() {
  const rings = [
    { r: 40, color: "#8b5cf6", dash: 62 },
    { r: 31, color: "#d946ef", dash: 78 },
    { r: 22, color: "#fb7185", dash: 40 },
  ];
  return (
    <svg viewBox="0 0 100 100" className="h-28 w-28 -rotate-90">
      {rings.map((ring) => {
        const c = 2 * Math.PI * ring.r;
        return (
          <g key={ring.r}>
            <circle cx="50" cy="50" r={ring.r} fill="none" stroke="currentColor" strokeWidth="7" className="text-primary/10" />
            <circle
              cx="50"
              cy="50"
              r={ring.r}
              fill="none"
              stroke={ring.color}
              strokeWidth="7"
              strokeLinecap="round"
              strokeDasharray={`${(ring.dash / 100) * c} ${c}`}
            />
          </g>
        );
      })}
    </svg>
  );
}

function Funnel({ stats, eur }: { stats: DashboardStats | null; eur: Intl.NumberFormat }) {
  const stages = [
    { label: "Nuovo lead", count: stats?.total_leads ?? 320, value: 125430, w: 100 },
    { label: "Qualificazione", count: 210, value: 98750, w: 86 },
    { label: "Proposta", count: 130, value: 75200, w: 72 },
    { label: "Negoziazione", count: 75, value: 45600, w: 58 },
    { label: "Chiuso vinto", count: 45, value: 32100, w: 44 },
  ];
  return (
    <div className="mt-4 space-y-1.5">
      {stages.map((s, i) => (
        <div key={s.label} className="flex items-center gap-3">
          <div className="flex flex-1 justify-center">
            <div
              className="rounded-md py-1.5 text-center text-[11px] font-semibold text-white shadow-sm"
              style={{
                width: `${s.w}%`,
                background: `linear-gradient(90deg, hsl(262 83% ${64 - i * 6}%), hsl(290 80% ${66 - i * 6}%))`,
              }}
            >
              {s.label}
            </div>
          </div>
          <div className="w-10 shrink-0 text-right text-xs font-semibold tabular-nums">{s.count}</div>
          <div className="w-20 shrink-0 text-right text-[11px] text-muted-foreground tabular-nums">{eur.format(s.value)}</div>
        </div>
      ))}
    </div>
  );
}

/* ───────────────────────── sample data (i18n + real wiring = fast-follow) ───────────────────────── */

const RECENT_ACTIVITIES = [
  { icon: Phone, title: "Chiamata con Mario Rossi", sub: "Discussione proposta commerciale", time: "Oggi, 10:30", status: "Completata" as const },
  { icon: Mail, title: "Invio preventivo a Bianchi SRL", sub: "Preventivo #1287", time: "Oggi, 09:15", status: "Completata" as const },
  { icon: CalendarDays, title: "Meeting con Verdi SpA", sub: "Presentazione nuovo progetto", time: "Ieri, 15:45", status: "In attesa" as const },
  { icon: Bell, title: "Follow-up Laura Neri", sub: "Richiesta informazioni", time: "Ieri, 11:20", status: "Completata" as const },
];

const MY_TASKS = [
  { title: "Chiamata con Mario Rossi", time: "10:30" },
  { title: "Invio preventivo a Bianchi SRL", time: "11:15" },
  { title: "Meeting con Verdi SpA", time: "14:30" },
  { title: "Follow-up Laura Neri", time: "16:00" },
  { title: "Report settimanale", time: "17:00" },
];

const COMPANIES = [
  { name: "Bianchi SRL", kind: "Azienda", initials: "B", color: "bg-gradient-to-br from-violet-500 to-indigo-500" },
  { name: "Verdi SpA", kind: "Azienda", initials: "V", color: "bg-gradient-to-br from-emerald-500 to-teal-500" },
  { name: "Rossi & Co.", kind: "Azienda", initials: "R", color: "bg-gradient-to-br from-fuchsia-500 to-pink-500" },
  { name: "Blu Solutions", kind: "Azienda", initials: "BS", color: "bg-gradient-to-br from-sky-500 to-blue-600" },
];

const DOCUMENTS = [
  { name: "Preventivo_1287_BianchiSRL.pdf", time: "Oggi, 09:15" },
  { name: "Contratto_VerdiSpA_2025.pdf", time: "Ieri, 14:20" },
  { name: "Fattura_2025_0456_RossiCo.pdf", time: "28 Mag 2025" },
];
