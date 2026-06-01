"use client";

import { useTranslations } from "next-intl";
import { LegalShell, LegalSection } from "@/components/marketing/legal-shell";

// Cookies Policy template. Covers the categories every GDPR/ePrivacy
// regulator expects to see — essential, functional, analytics, marketing
// — plus the third-party sub-processors common to a B2B SaaS stack
// (Stripe, Sentry, etc.). Wording is auditable boilerplate; refine the
// vendor list as the real stack evolves.

export default function CookiesPage() {
  const t = useTranslations("legal.cookies");

  return (
    <LegalShell title={t("title")} lastUpdated="2026-05-30">
      <p className="text-base leading-relaxed text-muted-foreground sm:text-lg">
        {t("intro")}
      </p>

      <LegalSection number={1} title={t("s1.title")}>
        <p>
          Cookies are small text files placed on your device when you visit a
          website. They are widely used to make websites work, or work more
          efficiently, as well as to provide information to the site owners.
          Similar technologies (local storage, pixels, SDKs) are covered by
          this policy where used by CRM Gallo.
        </p>
      </LegalSection>

      <LegalSection number={2} title={t("s2.title")}>
        <p>
          We use cookies to keep you signed in, remember your preferences,
          understand how the Service is used, and improve performance. We do
          not use cookies to build behavioural advertising profiles outside
          the Service.
        </p>
      </LegalSection>

      <LegalSection number={3} title={t("s3.title")}>
        <p>The cookies we set fall into four categories:</p>

        <div className="mt-4 space-y-4">
          <CookieCategory
            label={t("cat.essential.label")}
            tag="Required"
            description={t("cat.essential.body")}
            examples={[
              "auth_session — keeps you signed in",
              "csrf_token — prevents cross-site request forgery",
              "locale — remembers your language preference",
            ]}
          />
          <CookieCategory
            label={t("cat.functional.label")}
            tag="Optional"
            description={t("cat.functional.body")}
            examples={[
              "theme — light/dark/system preference",
              "sidebar_collapsed — UI layout state",
            ]}
          />
          <CookieCategory
            label={t("cat.analytics.label")}
            tag="Optional"
            description={t("cat.analytics.body")}
            examples={[
              "Aggregated page view counts (no PII)",
              "Performance traces for slow requests (Sentry)",
            ]}
          />
          <CookieCategory
            label={t("cat.marketing.label")}
            tag="Off by default"
            description={t("cat.marketing.body")}
            examples={[
              "Currently none — we will update this policy and request consent before any marketing cookie is set.",
            ]}
          />
        </div>
      </LegalSection>

      <LegalSection number={4} title={t("s4.title")}>
        <p>
          The following sub-processors may set cookies or use similar
          technologies when you interact with the Service:
        </p>
        <ul className="ml-6 list-disc space-y-1.5">
          <li>
            <span className="text-foreground/80">Stripe</span> — payment
            processing during checkout (
            <a
              href="https://stripe.com/cookie-settings"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              policy
            </a>
            ).
          </li>
          <li>
            <span className="text-foreground/80">Sentry</span> — error
            reporting and performance monitoring (
            <a
              href="https://sentry.io/privacy/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              policy
            </a>
            ).
          </li>
          <li>
            <span className="text-foreground/80">Cloudflare</span> — security
            and CDN delivery (
            <a
              href="https://www.cloudflare.com/cookie-policy/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              policy
            </a>
            ).
          </li>
        </ul>
      </LegalSection>

      <LegalSection number={5} title={t("s5.title")}>
        <p>
          Most browsers let you refuse or delete cookies through their
          settings. Blocking essential cookies will prevent the Service from
          working — for example, you will be signed out on every page load.
        </p>
        <p>
          You can also clear your local data at any time from your account
          settings. Once we ship our cookie banner (target Q3 2026) you will
          be able to enable or disable each optional category from a single
          control.
        </p>
      </LegalSection>

      <LegalSection number={6} title={t("s6.title")}>
        <p>
          We may update this Cookies Policy from time to time. The version
          posted at the top of this page always applies. Material changes
          will be announced in-app or by email where possible.
        </p>
      </LegalSection>

      <LegalSection number={7} title={t("s7.title")}>
        <p>
          For questions about this policy or to exercise your data-subject
          rights, email{" "}
          <a
            href="mailto:privacy@crmgallo.com"
            className="text-primary underline-offset-4 hover:underline"
          >
            privacy@crmgallo.com
          </a>
          .
        </p>
      </LegalSection>
    </LegalShell>
  );
}

function CookieCategory({
  label,
  tag,
  description,
  examples,
}: {
  label: string;
  tag: string;
  description: string;
  examples: string[];
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 backdrop-blur-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-foreground">{label}</span>
        <span className="rounded-full border border-white/15 bg-white/5 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          {tag}
        </span>
      </div>
      <p className="mt-2 text-sm text-muted-foreground">{description}</p>
      <ul className="mt-2 ml-5 list-disc space-y-1 text-xs text-muted-foreground/80">
        {examples.map((e) => (
          <li key={e}>{e}</li>
        ))}
      </ul>
    </div>
  );
}
