import { defineConfig, devices } from "@playwright/test";

/**
 * Config Playwright para smoke tests E2E.
 *
 * Sobe `vite preview` (servindo `dist/` ja compilado) e bate com Chromium
 * headless. Sem dependencia de stack docker — roda contra build estatico.
 *
 * Pra cobrir API/Ghost/auth real precisaria docker compose; ficou pra Onda 2.
 *
 * No CI: o job `e2e` (deploy-prd.yml) pula `npm run build` e baixa o artifact
 * `ui-dist` do job `ui-validate` (evita rebuild duplicado).
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  // 1 worker por classe pra tornar resultados determinist em smoke.
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",

  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: {
    command: "npm run preview -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173/app/",
    timeout: 60_000,
    reuseExistingServer: !process.env.CI,
  },
});
