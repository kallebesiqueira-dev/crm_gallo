"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import {
  Cloud,
  Cpu,
  CreditCard,
  Facebook,
  Instagram,
  Linkedin,
  Lock,
  Mail,
  ShieldCheck,
  Sparkles,
  Youtube,
} from "lucide-react";
import { Logo } from "@/components/logo";
import { cn } from "@/lib/utils";

/**
 * Landing footer — multi-tier layout inspired by Datacrazy.
 *
 *   1. Tech-partners band: badge + headline + body on the left, a row of
 *      glowing partner discs on the right.
 *   2. Main grid: brand block (logo + tagline + social row) + 3 link
 *      columns (Product / Legal / Company) + company-info block (VAT,
 *      addresses, copyright).
 *   3. Bottom watermark: huge gradient "GALLO CRM" wordmark that bleeds
 *      to the edges, identical in spirit to the Datacrazy footer mark.
 *
 * Everything renders on the page-level <FuturisticBackground> — no opaque
 * background of its own so the mesh shows through.
 */

interface PartnerDisc {
  id: string;
  Icon: typeof Sparkles;
  // Tailwind from→to gradient classes for the disc fill + the glow halo.
  gradient: string;
  glow: string;
}

const PARTNERS: PartnerDisc[] = [
  { id: "security",       Icon: ShieldCheck, gradient: "from-blue-500 to-cyan-500",     glow: "bg-blue-500/40" },
  { id: "ai",             Icon: Cpu,         gradient: "from-violet-500 to-fuchsia-500", glow: "bg-violet-500/40" },
  { id: "payments",       Icon: CreditCard,  gradient: "from-amber-500 to-orange-500",   glow: "bg-amber-500/40" },
  { id: "infrastructure", Icon: Cloud,       gradient: "from-emerald-500 to-teal-500",   glow: "bg-emerald-500/40" },
  { id: "privacy",        Icon: Lock,        gradient: "from-rose-500 to-pink-500",      glow: "bg-rose-500/40" },
];

interface SocialLink {
  id: string;
  label: string;
  href: string;
  // lucide-react component or null for inline-SVG specials (WhatsApp).
  Icon: typeof Sparkles | null;
}

// All hrefs are placeholders for now. Wire them to real accounts when
// the channels go live; the design holds either way.
const SOCIAL_LINKS: SocialLink[] = [
  { id: "whatsapp",  label: "WhatsApp",  href: "https://wa.me/393717403464", Icon: null },
  { id: "instagram", label: "Instagram", href: "#",                       Icon: Instagram },
  { id: "facebook",  label: "Facebook",  href: "#",                       Icon: Facebook },
  { id: "linkedin",  label: "LinkedIn",  href: "#",                       Icon: Linkedin },
  { id: "youtube",   label: "YouTube",   href: "#",                       Icon: Youtube },
  { id: "email",     label: "Email",     href: "mailto:gallo-crm@hotmail.com", Icon: Mail },
];

export function Footer() {
  const t = useTranslations("pricing");
  const tApp = useTranslations("app");
  const tMarketing = useTranslations("marketing");
  const locale = useLocale();

  const year = new Date().getFullYear();

  return (
    <footer className="relative">
      {/* ============== Tech-partners band ============== */}
      <div>
        <div className="mx-auto max-w-7xl px-6 py-14 lg:py-16">
          <div className="flex flex-col items-start justify-between gap-10 lg:flex-row lg:items-center lg:gap-16">
            {/* Copy */}
            <div className="max-w-xl">
              <div className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-xs font-semibold backdrop-blur-xl">
                <Sparkles className="h-3 w-3 text-blue-400" />
                {tMarketing("footerPartnersBadge")}
              </div>
              <h3 className="mt-5 text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
                {tMarketing("footerPartnersTitle")}
              </h3>
              <p className="mt-3 text-sm text-muted-foreground sm:text-base">
                {tMarketing("footerPartnersBody")}
              </p>
            </div>

            {/* Partner discs — glowing circular icons that pick up the
                mesh palette. Each disc gets its own halo via a -z-10
                blurred sibling, so the glow reads as ambient light. */}
            <div className="flex flex-wrap items-center gap-4 sm:gap-5">
              {PARTNERS.map(({ id, Icon, gradient, glow }) => (
                <div key={id} className="relative">
                  <div
                    aria-hidden
                    className={cn(
                      "pointer-events-none absolute -inset-1 -z-10 rounded-full blur-md",
                      glow,
                    )}
                  />
                  <div
                    aria-label={tMarketing(`footerPartners.${id}`)}
                    className={cn(
                      "grid h-14 w-14 place-items-center rounded-full border border-white/15 bg-gradient-to-br text-white shadow-xl transition-transform hover:scale-110 sm:h-16 sm:w-16",
                      gradient,
                    )}
                  >
                    <Icon className="h-5 w-5 sm:h-6 sm:w-6" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ============== Main grid ============== */}
      <div className="mx-auto max-w-7xl px-6 py-14">
        <div className="grid gap-10 lg:grid-cols-12">
          {/* Brand block */}
          <div className="lg:col-span-4">
            <Logo size="md" priority={false} label={tApp("name")} />
            <p className="mt-4 max-w-xs text-sm text-muted-foreground">
              {tMarketing("footerTagline")}
            </p>

            {/* Social row — the copyright/license line lives below the
                whole main grid, centred, so it reads as the footer's true
                bottom line rather than a column footer. */}
            <div className="mt-6 flex flex-wrap items-center gap-2">
              {SOCIAL_LINKS.map((s) => (
                <a
                  key={s.id}
                  href={s.href}
                  aria-label={s.label}
                  target={s.href.startsWith("http") ? "_blank" : undefined}
                  rel={s.href.startsWith("http") ? "noopener noreferrer" : undefined}
                  className="grid h-9 w-9 place-items-center rounded-lg border border-white/10 bg-white/5 text-muted-foreground transition-all duration-[200ms] hover:-translate-y-0.5 hover:scale-110 hover:border-white/30 hover:bg-white/10 hover:text-foreground"
                >
                  {s.Icon ? (
                    <s.Icon className="h-4 w-4" />
                  ) : (
                    /* WhatsApp — lucide-react doesn't ship it, so we
                       inline the official mark trimmed to 24×24. */
                    <svg
                      viewBox="0 0 24 24"
                      className="h-4 w-4"
                      fill="currentColor"
                      aria-hidden
                    >
                      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z" />
                    </svg>
                  )}
                </a>
              ))}
            </div>
          </div>

          {/* Product */}
          <div className="lg:col-span-2">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {tMarketing("footerProduct")}
            </div>
            <ul className="mt-4 space-y-2.5 text-sm">
              <li><Link href={`/${locale}#features`} className="text-muted-foreground transition-colors hover:text-foreground">{tMarketing("navFeatures")}</Link></li>
              <li><Link href={`/${locale}#pricing`} className="text-muted-foreground transition-colors hover:text-foreground">{tMarketing("navPricing")}</Link></li>
              <li><Link href={`/${locale}#manifesto`} className="text-muted-foreground transition-colors hover:text-foreground">{tMarketing("navManifesto")}</Link></li>
              <li><Link href={`/${locale}#faq`} className="text-muted-foreground transition-colors hover:text-foreground">{tMarketing("navFaq")}</Link></li>
              <li><Link href={`/${locale}/login`} className="text-muted-foreground transition-colors hover:text-foreground">{t("signIn")}</Link></li>
            </ul>
          </div>

          {/* Legal */}
          <div className="lg:col-span-2">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {tMarketing("footerLegal")}
            </div>
            <ul className="mt-4 space-y-2.5 text-sm">
              <li><Link href={`/${locale}/terms`} className="text-muted-foreground transition-colors hover:text-foreground">{tMarketing("footerTerms")}</Link></li>
              <li><Link href={`/${locale}/cookies`} className="text-muted-foreground transition-colors hover:text-foreground">{tMarketing("footerCookies")}</Link></li>
              <li><span className="text-muted-foreground/50" title="Coming soon">{tMarketing("footerPrivacy")}</span></li>
              <li><span className="text-muted-foreground/50" title="Coming soon">{tMarketing("footerSecurity")}</span></li>
            </ul>
          </div>

          {/* Company info — full legal registry record. Two-column dl/dt/dd
              keeps the labels aligned at a fixed width so the values stack
              cleanly, and phone/email/site become real interactive links
              (tel: / mailto: / https://). */}
          <div className="lg:col-span-4">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {tMarketing("footerCompany")}
            </div>
            <dl className="mt-4 grid grid-cols-[8rem_1fr] gap-x-3 gap-y-2 text-xs leading-relaxed text-muted-foreground">
              {/* Real registered entity: GALLO CRM S.r.l., Marchirolo (VA),
                  Partita IVA IT03270000777. */}
              <dt className="text-foreground/80">{tMarketing("footerBusinessName")}</dt>
              <dd className="break-words">GALLO CRM S.r.l.</dd>

              <dt className="text-foreground/80">{tMarketing("footerVAT")}</dt>
              <dd className="font-mono break-words">IT03270000777</dd>

              <dt className="text-foreground/80">{tMarketing("footerAddress")}</dt>
              <dd className="break-words">
                Via Statale 21
                <br />
                21030 Marchirolo (VA), Italia
              </dd>

              <dt className="text-foreground/80">{tMarketing("footerPhone")}</dt>
              <dd>
                <a
                  href="tel:+393717403464"
                  className="font-mono break-words transition-colors hover:text-foreground"
                >
                  +39 371 740 3464
                </a>
              </dd>

              <dt className="text-foreground/80">{tMarketing("footerEmail")}</dt>
              <dd>
                <a
                  href="mailto:gallo-crm@hotmail.com"
                  className="break-words transition-colors hover:text-foreground"
                >
                  gallo-crm@hotmail.com
                </a>
              </dd>

              <dt className="text-foreground/80">{tMarketing("footerWebsite")}</dt>
              <dd>
                <a
                  href="https://www.gallo-crm.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="break-words transition-colors hover:text-foreground"
                >
                  www.gallo-crm.com
                </a>
              </dd>
            </dl>
          </div>
        </div>

        {/* Centred copyright line — the footer's true bottom credit, set
            beneath the whole main grid so it spans full width. */}
        <p className="mt-10 text-center text-xs text-muted-foreground/70">
          © {year} {tApp("name")} · AGPL-3.0 · {tMarketing("footerRightsReserved")}
        </p>
      </div>

      {/* ============== Watermark wordmark ============== */}
      {/* Gigantic gradient-clipped wordmark — last beat of brand presence
          before the user leaves. Hovering the letters triggers a soft
          "bubble inflate": springy cubic-bezier scale + intensified
          gradient + glow, like a balloon swelling under the cursor. */}
      <div className="group relative overflow-hidden">
        <div
          aria-hidden
          className="mx-auto max-w-[1600px] cursor-default px-2 py-6 text-center"
        >
          <span
            className="inline-block bg-gradient-to-b from-white/10 via-white/[0.04] to-transparent bg-clip-text font-bold leading-[0.85] tracking-tighter text-transparent transition-all duration-[700ms] ease-[cubic-bezier(0.34,1.56,0.64,1)] group-hover:scale-[1.04] group-hover:from-white/35 group-hover:via-white/15 group-hover:drop-shadow-[0_20px_80px_rgba(168,85,247,0.45)]"
            style={{ fontSize: "clamp(4rem, 18vw, 16rem)" }}
          >
            GALLO CRM
          </span>
        </div>
      </div>
    </footer>
  );
}
