"use client";

import { LegalShell, LegalSection } from "@/components/marketing/legal-shell";

// Data Security overview. Describes the technical and organisational measures
// actually implemented in the platform. Keep this in sync with reality — it is
// a public commitment, not marketing. Contact: gallo-crm@hotmail.com.

const CONTACT = "gallo-crm@hotmail.com";

export default function SecurityPage() {
  return (
    <LegalShell title="Data Security" lastUpdated="2026-06-08">
      <p className="text-base leading-relaxed text-muted-foreground sm:text-lg">
        Security is foundational to Gallo CRM. This page summarises the
        technical and organisational measures we use to protect your data. If
        you have a question or want to report a vulnerability, contact{" "}
        <a href={`mailto:${CONTACT}`} className="text-primary underline-offset-4 hover:underline">
          {CONTACT}
        </a>
        .
      </p>

      <LegalSection number={1} title="Encryption">
        <p>
          All traffic to and from the Service is encrypted in transit with TLS
          (HTTPS). Data at rest — including your database records and uploaded
          files — is encrypted by our infrastructure providers.
        </p>
      </LegalSection>

      <LegalSection number={2} title="Tenant isolation">
        <p>
          Every organisation&rsquo;s data is logically separated. We enforce
          isolation at the database layer using PostgreSQL Row-Level Security:
          the application connects through a restricted role that has{" "}
          <span className="font-mono text-foreground/80">NOSUPERUSER</span> and{" "}
          <span className="font-mono text-foreground/80">NOBYPASSRLS</span>, so
          row-level policies are enforced on every query and one tenant cannot
          read another tenant&rsquo;s rows.
        </p>
      </LegalSection>

      <LegalSection number={3} title="Authentication &amp; access">
        <ul className="ml-6 list-disc space-y-1.5">
          <li>Passwords are stored only as salted bcrypt hashes — never in plain text.</li>
          <li>Sessions use signed JWTs delivered over secure, HTTP-only cookies with CSRF protection.</li>
          <li>Two-factor authentication (TOTP) is available, and can be required for privileged roles.</li>
          <li>Sensitive endpoints (login, registration, password reset) are rate-limited per IP.</li>
          <li>Access follows the principle of least privilege, both for application roles and our team.</li>
        </ul>
      </LegalSection>

      <LegalSection number={4} title="Infrastructure &amp; data residency">
        <p>
          The application, database and file storage run on managed, EU-region
          infrastructure. Uploaded files are stored in object storage with EU
          data residency. Services run in isolated containers, and credentials
          are supplied through the environment — never committed to source code.
        </p>
      </LegalSection>

      <LegalSection number={5} title="Monitoring &amp; auditing">
        <p>
          Security-relevant actions are recorded in an append-only audit log.
          We use EU-region error and performance monitoring to detect and
          respond to issues quickly. Logs are retained for a limited period and
          access to them is restricted.
        </p>
      </LegalSection>

      <LegalSection number={6} title="Secure development">
        <ul className="ml-6 list-disc space-y-1.5">
          <li>Automated secret scanning runs on every change to prevent credentials reaching the codebase.</li>
          <li>Dependencies and container images are scanned for known vulnerabilities in our CI pipeline.</li>
          <li>Changes are reviewed before they reach production, and an automated test suite gates releases.</li>
        </ul>
      </LegalSection>

      <LegalSection number={7} title="Backups &amp; resilience">
        <p>
          The managed database is backed up automatically on a rolling schedule
          so data can be recovered in the event of an incident. We design the
          system to fail safe and to limit the blast radius of any single
          component failure.
        </p>
      </LegalSection>

      <LegalSection number={8} title="Payments">
        <p>
          Payments are handled by Stripe, a PCI-DSS Level 1 certified provider.
          Card details are entered directly with Stripe and are never seen or
          stored by Gallo CRM — we only keep the resulting non-sensitive
          identifiers needed to manage your subscription.
        </p>
      </LegalSection>

      <LegalSection number={9} title="Subprocessors">
        <p>
          We work with a small, vetted set of providers (hosting, storage,
          payments, email, AI and monitoring), each under a data-processing
          agreement. See our Privacy Policy for the current list and the
          purpose of each.
        </p>
      </LegalSection>

      <LegalSection number={10} title="Reporting a vulnerability">
        <p>
          We welcome responsible disclosure. If you believe you have found a
          security issue, please email{" "}
          <a href={`mailto:${CONTACT}`} className="text-primary underline-offset-4 hover:underline">
            {CONTACT}
          </a>{" "}
          with enough detail to reproduce it. Please give us reasonable time to
          remediate before any public disclosure, and do not access or modify
          data that is not yours.
        </p>
      </LegalSection>

      <LegalSection number={11} title="Contact">
        <p>
          Security questions? Email{" "}
          <a href={`mailto:${CONTACT}`} className="text-primary underline-offset-4 hover:underline">
            {CONTACT}
          </a>
          .
        </p>
      </LegalSection>
    </LegalShell>
  );
}
