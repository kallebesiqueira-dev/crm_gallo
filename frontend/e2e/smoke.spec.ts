import { expect, test, type Page } from "@playwright/test";

// Two e2e smokes against an already-running full stack (see playwright.config.ts).
// Both run on the `/en` locale so the (i18n) button labels are deterministic
// ("Sign out", "Save", "Score with AI").
//
//   1. "core golden path" — register → sign out → log in → create a lead →
//      sign out. Fast (~30s) and fully deterministic, so it's the per-PR CI
//      gate. No LLM in the loop.
//   2. "AI scoring" — register → create a lead → score it. The scorer calls a
//      local Ollama model inline, which on modest hardware takes ~2-3 minutes
//      and varies run to run, so it is NOT a per-PR gate. It is skipped unless
//      SCORE_E2E is set (manual / nightly), keeping CI fast and deterministic.
//
// Seat-cap note: each test registers a fresh account, and every plain signup
// joins the install-wide `default-workspace` org (Free plan caps it at 2
// seats). A fresh stack bootstraps that org empty, so the core test's single
// register always fits. Re-running against a dirty local DB can hit the 402
// seat cap — start from a clean stack (or bump the org's plan) when iterating.
//
// Founder note: the very first account on a clean stack is the install founder,
// which the API auto-verifies and logs straight into the dashboard. Every later
// signup must click an email-verification link we can't follow headless, so
// these smokes rely on the per-run fresh stack (the CI job tears the DB down and
// back up) making each test's single register the founder.

const PASSWORD = "PlaywrightPass2026!";

// The "Sign out" button renders only once the authenticated app layout is
// interactive (i.e. `me()` has resolved). It carries no viewport-specific
// `hidden` class, so it's a stable hydration signal on any authed page — unlike
// the header identity, which shows the full name (not the email) and only from
// the `xl` breakpoint.
async function expectAppShell(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({ timeout: 30_000 });
}

// Register a fresh account (the founder on a clean stack — see the note above).
// The password-strength label ("Strong") is rendered from React state, so
// waiting for it proves the register page has hydrated before we submit.
async function register(page: Page): Promise<string> {
  const email = `e2e+${Date.now()}@example.com`;
  await page.goto("/en/register");
  await page.locator("#full_name").fill("E2E Tester");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(PASSWORD);
  await expect(page.getByText("Strong")).toBeVisible({ timeout: 15_000 });
  await page.locator('input[type="checkbox"]').check(); // accept terms
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/en\/dashboard/, { timeout: 30_000 });
  await expectAppShell(page);
  return email;
}

// Create a lead and assert we land on its detail page. Waiting for the app
// shell first proves the layout is interactive (the form's onSubmit is wired)
// before we fill and submit.
async function createLead(page: Page): Promise<void> {
  await page.goto("/en/leads/new");
  await expectAppShell(page);
  await page.locator("#first_name").fill("Ada");
  await page.locator("#last_name").fill("Lovelace");
  await page.locator("#email").fill(`lead+${Date.now()}@example.com`);
  await page.locator("#company").fill("Analytical Engines Ltd");
  await page.locator('button[type="submit"]').click();
  // Redirects to the lead detail page (/en/leads/{uuid}).
  await expect(page).toHaveURL(/\/en\/leads\/[0-9a-f-]{36}/, { timeout: 30_000 });
  await expect(page.getByText("Ada Lovelace")).toBeVisible({ timeout: 30_000 });
}

test("core golden path: register, login, create lead, logout", async ({ page }) => {
  const email = await register(page);

  // --- sign out, then log back in with the same credentials ---
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/en\/login/);

  await page.locator("#email").fill(email);
  await page.locator("#password").fill(PASSWORD);
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/en\/dashboard/, { timeout: 30_000 });
  await expectAppShell(page);

  // --- create a lead ---
  await createLead(page);

  // --- final sign out ---
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/en\/login/);
});

test("AI scoring assigns a priority", async ({ page }) => {
  test.skip(
    !process.env.SCORE_E2E,
    "Set SCORE_E2E=1 to run the LLM-backed scoring smoke (slow: ~2-3 min, needs a warm Ollama model).",
  );
  // The inline LLM call is the slow link (a cold local model can take a
  // minute-plus), so give this test its own generous budget.
  test.setTimeout(300_000);

  await register(page);
  await createLead(page);

  // The "Priority:" line only renders once a score lands, so it's the signal
  // that scoring succeeded.
  await page.getByRole("button", { name: "Score with AI" }).click();
  await expect(page.getByText("Priority:")).toBeVisible({ timeout: 240_000 });
});
