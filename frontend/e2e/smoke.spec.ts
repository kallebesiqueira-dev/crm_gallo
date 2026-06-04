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

const PASSWORD = "PlaywrightPass2026!";

// Register a fresh free-plan account. Registration auto-authenticates and
// lands on the dashboard. The password-strength label ("Strong") is rendered
// from React state, so waiting for it proves the page has hydrated — i.e. the
// form's onSubmit is wired and our click won't drop into a pre-hydration void.
// We then wait for the email in the app-layout header (rendered only after
// `me()` resolves) so callers start from a fully interactive dashboard.
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
  await expect(page.getByText(email)).toBeVisible({ timeout: 30_000 });
  return email;
}

// Create a lead and assert we land on its detail page. `email` is the header
// hydration guard: the form's onSubmit is wired only once the app layout is
// interactive (header email present).
async function createLead(page: Page, email: string): Promise<void> {
  await page.goto("/en/leads/new");
  await expect(page.getByText(email)).toBeVisible({ timeout: 30_000 });
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
  await expect(page.getByText(email)).toBeVisible({ timeout: 30_000 });

  // --- create a lead ---
  await createLead(page, email);

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

  const email = await register(page);
  await createLead(page, email);

  // The "Priority:" line only renders once a score lands, so it's the signal
  // that scoring succeeded.
  await page.getByRole("button", { name: "Score with AI" }).click();
  await expect(page.getByText("Priority:")).toBeVisible({ timeout: 240_000 });
});
