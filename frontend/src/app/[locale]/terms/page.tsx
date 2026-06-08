"use client";

import { useTranslations } from "next-intl";
import { LegalShell, LegalSection } from "@/components/marketing/legal-shell";

// Plain-English Terms of Service template — the structure mirrors what
// every B2B SaaS legal team ships on day one. Wording is intentionally
// neutral so a real lawyer can refine it without rearchitecting the page.
// Localise the body strings before going live in a non-EN market.

export default function TermsPage() {
  const t = useTranslations("legal.terms");

  return (
    <LegalShell title={t("title")} lastUpdated="2026-05-30">
      <p className="text-base leading-relaxed text-muted-foreground sm:text-lg">
        {t("intro")}
      </p>

      <LegalSection number={1} title={t("s1.title")}>
        <p>
          By accessing or using Gallo CRM (the &ldquo;Service&rdquo;), you
          agree to be bound by these Terms of Service and our Privacy Policy.
          If you do not agree, you must not access or use the Service.
        </p>
        <p>
          We may update these Terms from time to time. The version posted at
          the top of this page always applies. Continued use of the Service
          after a change constitutes acceptance of the revised Terms.
        </p>
      </LegalSection>

      <LegalSection number={2} title={t("s2.title")}>
        <p>
          Gallo CRM is a multilingual, AI-assisted customer relationship
          management platform offered as a hosted service and as open-source
          software under the GNU AGPL-3.0 licence. Self-hosted deployments
          are governed by the AGPL-3.0 licence text rather than by these
          Terms.
        </p>
      </LegalSection>

      <LegalSection number={3} title={t("s3.title")}>
        <p>
          To use the Service you must create an account. You agree to
          provide accurate, current and complete information, to keep it
          up to date, and to safeguard your credentials. You are responsible
          for all activity that occurs under your account.
        </p>
        <p>
          You must be at least 18 years old (or the age of legal majority in
          your jurisdiction) and have authority to enter into binding
          agreements on behalf of any organisation you represent.
        </p>
      </LegalSection>

      <LegalSection number={4} title={t("s4.title")}>
        <p>
          Paid plans are billed through Stripe in the currency shown at
          checkout. Subscriptions auto-renew at the end of each billing
          cycle unless cancelled. You can cancel at any time from the
          Customer Portal; cancellation takes effect at the end of the
          current period.
        </p>
        <p>
          Fees are non-refundable except where required by law. If a charge
          fails after reasonable retry, we may suspend the affected features
          until the balance is settled.
        </p>
      </LegalSection>

      <LegalSection number={5} title={t("s5.title")}>
        <p>You agree not to:</p>
        <ul className="ml-6 list-disc space-y-1.5">
          <li>Use the Service to violate any law or third-party right;</li>
          <li>
            Upload content that is unlawful, infringing, defamatory, harmful
            or that contains malware;
          </li>
          <li>
            Reverse-engineer, decompile, or attempt to extract source code
            from non-AGPL components of the Service;
          </li>
          <li>
            Interfere with or disrupt the Service, its servers, or networks;
          </li>
          <li>
            Use automated means to access the Service in a manner that
            degrades performance for other users.
          </li>
        </ul>
      </LegalSection>

      <LegalSection number={6} title={t("s6.title")}>
        <p>
          You retain ownership of all data you upload (&ldquo;Customer
          Data&rdquo;). You grant us a worldwide, non-exclusive licence to
          host, process, transmit and display that data solely to provide
          and improve the Service.
        </p>
        <p>
          The Gallo CRM software is licensed, not sold. Our trademarks, logos
          and branding remain our property. The platform&rsquo;s source code is
          released under the AGPL-3.0 licence and may be used and modified
          accordingly.
        </p>
      </LegalSection>

      <LegalSection number={7} title={t("s7.title")}>
        <p>
          We process personal data in accordance with our Privacy Policy and
          applicable laws including the GDPR. You are responsible for
          ensuring you have a lawful basis to upload personal data about
          third parties to the Service.
        </p>
        <p>
          We do not sell Customer Data. We do not use Customer Data to train
          third-party AI models without your explicit opt-in. AI features
          process data on a per-request basis only.
        </p>
      </LegalSection>

      <LegalSection number={8} title={t("s8.title")}>
        <p>
          We aim to keep the Service available 24/7 but do not guarantee
          uninterrupted access. We may schedule maintenance windows and
          will give reasonable notice where practical. Service Level
          commitments, where offered, are stated in your specific plan or
          order form.
        </p>
      </LegalSection>

      <LegalSection number={9} title={t("s9.title")}>
        <p>
          You may terminate your account at any time. We may suspend or
          terminate your access if you breach these Terms or if required by
          law. On termination we will retain Customer Data for 30 days to
          allow recovery, then delete it on request.
        </p>
      </LegalSection>

      <LegalSection number={10} title={t("s10.title")}>
        <p>
          To the maximum extent permitted by law, the Service is provided
          &ldquo;as is&rdquo; without warranties of any kind. We are not
          liable for indirect, incidental, consequential, special or
          exemplary damages. Our total liability arising out of or related
          to the Service shall not exceed the fees paid by you in the twelve
          months preceding the event giving rise to the claim.
        </p>
      </LegalSection>

      <LegalSection number={11} title={t("s11.title")}>
        <p>
          You agree to indemnify and hold Gallo CRM harmless from any
          claims, losses or expenses (including reasonable legal fees)
          arising from your use of the Service or breach of these Terms.
        </p>
      </LegalSection>

      <LegalSection number={12} title={t("s12.title")}>
        <p>
          These Terms are governed by the laws of Italy. Any dispute will
          be submitted to the exclusive jurisdiction of the courts of
          Milan, Italy, except where consumer-protection law of your
          jurisdiction requires otherwise.
        </p>
      </LegalSection>

      <LegalSection number={13} title={t("s13.title")}>
        <p>
          Questions about these Terms? Email{" "}
          <a
            href="mailto:gallo-crm@hotmail.com"
            className="text-primary underline-offset-4 hover:underline"
          >
            gallo-crm@hotmail.com
          </a>
          .
        </p>
      </LegalSection>
    </LegalShell>
  );
}
