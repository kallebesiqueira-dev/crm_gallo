import { defineConfig, devices } from "@playwright/test";

// E2E runs against an already-running full stack (frontend + backend + db +
// redis + worker + ollama). Locally that's the docker-compose stack — the
// frontend is published on :3030, the API on :8001. Override the base URL via
// PLAYWRIGHT_BASE_URL when pointing at a different host (e.g. CI / staging).
// No `webServer` block on purpose: the API/worker/LLM can't be spun up by
// Playwright alone, so we never want it silently launching a half-stack.
const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3030";

export default defineConfig({
  testDir: "./e2e",
  // The AI-scoring step calls the LLM inline, which is the slow link in the
  // chain (a cold local model can take a minute-plus), so the per-test budget
  // is deliberately large.
  timeout: 240_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
