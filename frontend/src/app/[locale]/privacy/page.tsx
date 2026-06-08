"use client";

import { LegalShell, LegalSection } from "@/components/marketing/legal-shell";

// Plain-English, GDPR-aware Privacy Policy template. Like the Terms page,
// the body copy is intentionally neutral so a real lawyer/DPO can refine it
// before relying on it. Localise the strings before going live in a
// non-EN market. Contact address: gallo-crm@hotmail.com.

const CONTACT = "gallo-crm@hotmail.com";

export default function PrivacyPage() {
  return (
    <LegalShell title="Privacy Policy" lastUpdated="2026-06-08">
      <p className="text-base leading-relaxed text-muted-foreground sm:text-lg">
        This Privacy Policy explains what personal data GALLO CRM S.r.l.
        (&ldquo;Gallo CRM&rdquo;, &ldquo;we&rdquo;, &ldquo;us&rdquo;) collects,
        why we process it, who we share it with, and the rights you have under
        the EU General Data Protection Regulation (GDPR) and other applicable
        laws.
      </p>

      <LegalSection number={1} title="Who we are (Data Controller)">
        <p>
          The data controller is <strong>GALLO CRM S.r.l.</strong>, Via Statale
          21, 21030 Marchirolo (VA), Italy — VAT IT03270000777. For any privacy
          request you can reach us at{" "}
          <a href={`mailto:${CONTACT}`} className="text-primary underline-offset-4 hover:underline">
            {CONTACT}
          </a>
          .
        </p>
        <p>
          When you upload information about your own customers and contacts
          (&ldquo;Customer Data&rdquo;), you act as the data controller for that
          data and Gallo CRM acts as your data processor, processing it on your
          instructions to provide the Service.
        </p>
      </LegalSection>

      <LegalSection number={2} title="Data we collect">
        <ul className="ml-6 list-disc space-y-1.5">
          <li>
            <strong>Account data:</strong> name, email address, password (stored
            only as a salted hash), organisation name, role, and language
            preference.
          </li>
          <li>
            <strong>Customer Data:</strong> the records you create or import —
            leads, customers, companies, deals, tasks, notes, files and the
            contact details they contain. You decide what to upload.
          </li>
          <li>
            <strong>Billing data:</strong> plan, subscription status and the
            payment identifiers returned by our payment processor. We never see
            or store your full card number.
          </li>
          <li>
            <strong>Technical &amp; usage data:</strong> IP address, device and
            browser information, and diagnostic/error events needed to operate
            and secure the Service.
          </li>
        </ul>
      </LegalSection>

      <LegalSection number={3} title="Why we process it and our legal basis">
        <ul className="ml-6 list-disc space-y-1.5">
          <li>
            <strong>To provide the Service</strong> (create your account, store
            and display your data, run features) — <em>performance of a
            contract</em> (GDPR Art. 6(1)(b)).
          </li>
          <li>
            <strong>To bill you</strong> for paid plans — <em>contract</em> and{" "}
            <em>legal obligation</em> (tax/accounting).
          </li>
          <li>
            <strong>To secure and improve the Service</strong> (rate limiting,
            fraud and abuse prevention, error monitoring, aggregated analytics) —{" "}
            <em>legitimate interests</em> (Art. 6(1)(f)).
          </li>
          <li>
            <strong>To send transactional emails</strong> (invites, password
            resets, billing notices) — <em>contract</em>.
          </li>
          <li>
            <strong>Where required, with your consent</strong> (e.g. optional AI
            features over your data) — <em>consent</em> (Art. 6(1)(a)), which you
            can withdraw at any time.
          </li>
        </ul>
      </LegalSection>

      <LegalSection number={4} title="AI features">
        <p>
          Some optional features (lead scoring, summarisation and the assistant)
          process the relevant records using third-party AI providers, including
          Anthropic. Depending on the configured provider this may involve a
          transfer of the processed records outside the EEA (e.g. to the United
          States) for the duration of the request only.
        </p>
        <p>
          We do <strong>not</strong> sell your data and we do{" "}
          <strong>not</strong> allow it to be used to train third-party AI models
          without your explicit opt-in. AI processing happens on a per-request
          basis; the providers act as our subprocessors under data-processing
          terms. You can disable AI features for your organisation.
        </p>
      </LegalSection>

      <LegalSection number={5} title="Subprocessors">
        <p>
          We rely on a small set of vetted providers to run the Service. Each
          processes data only as needed for its function and under a
          data-processing agreement:
        </p>
        <ul className="ml-6 list-disc space-y-1.5">
          <li><strong>Railway</strong> — application &amp; database hosting (EU region).</li>
          <li><strong>Cloudflare R2</strong> — file/attachment storage (EU jurisdiction).</li>
          <li><strong>Stripe</strong> — subscription billing and payment processing.</li>
          <li><strong>Resend</strong> — transactional email delivery.</li>
          <li><strong>Anthropic</strong> — AI processing for optional features (may involve a US transfer).</li>
          <li><strong>Sentry</strong> — error and performance monitoring (EU region).</li>
        </ul>
        <p>
          We will keep this list current and give notice of material changes.
          Contact us for the up-to-date subprocessor list at any time.
        </p>
      </LegalSection>

      <LegalSection number={6} title="International data transfers">
        <p>
          We host customer content in the EU. Some subprocessors (notably AI
          providers) may process data outside the EEA. Where that happens we
          rely on appropriate safeguards under GDPR Chapter V, such as the
          European Commission&rsquo;s Standard Contractual Clauses, and we
          minimise the data involved.
        </p>
      </LegalSection>

      <LegalSection number={7} title="Data retention">
        <p>
          We keep Customer Data for as long as your account is active. After you
          close your account we retain it for up to 30 days to allow recovery,
          then delete or anonymise it, except where a longer period is required
          by law (e.g. invoices for tax purposes). Backups are rotated on a
          rolling schedule.
        </p>
      </LegalSection>

      <LegalSection number={8} title="Your rights">
        <p>Subject to applicable law, you have the right to:</p>
        <ul className="ml-6 list-disc space-y-1.5">
          <li>access the personal data we hold about you;</li>
          <li>rectify inaccurate data and complete incomplete data;</li>
          <li>erase your data (&ldquo;right to be forgotten&rdquo;);</li>
          <li>restrict or object to certain processing;</li>
          <li>receive your data in a portable, machine-readable format;</li>
          <li>withdraw consent at any time, without affecting prior processing.</li>
        </ul>
        <p>
          To exercise any right, email{" "}
          <a href={`mailto:${CONTACT}`} className="text-primary underline-offset-4 hover:underline">
            {CONTACT}
          </a>
          . You also have the right to lodge a complaint with your local data
          protection authority (in Italy, the Garante per la protezione dei dati
          personali).
        </p>
      </LegalSection>

      <LegalSection number={9} title="Cookies">
        <p>
          We use only the cookies needed to run the Service (e.g. authentication
          and security) plus, where applicable, privacy-respecting analytics. See
          our Cookie Policy for details and your choices.
        </p>
      </LegalSection>

      <LegalSection number={10} title="Security">
        <p>
          We apply technical and organisational measures to protect your data,
          including encryption in transit, strict per-tenant isolation,
          least-privilege access and monitoring. See our Data Security page for
          details.
        </p>
      </LegalSection>

      <LegalSection number={11} title="Children">
        <p>
          The Service is intended for business use and is not directed to
          children. We do not knowingly collect personal data from anyone under
          18. If you believe a minor has provided us data, contact us and we will
          delete it.
        </p>
      </LegalSection>

      <LegalSection number={12} title="Changes to this policy">
        <p>
          We may update this Privacy Policy from time to time. The version shown
          at the top of this page always applies. We will notify you of material
          changes through the Service or by email.
        </p>
      </LegalSection>

      <LegalSection number={13} title="Contact">
        <p>
          Questions about your privacy or this policy? Email{" "}
          <a href={`mailto:${CONTACT}`} className="text-primary underline-offset-4 hover:underline">
            {CONTACT}
          </a>
          .
        </p>
      </LegalSection>
    </LegalShell>
  );
}
