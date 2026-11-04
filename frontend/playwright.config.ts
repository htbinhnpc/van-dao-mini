import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e", fullyParallel: true, workers: 3, retries: 0,
  timeout: 60_000, expect: { timeout: 10000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: "http://127.0.0.1:4175", reducedMotion: "reduce", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1040 } } },
    { name: "mobile", use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" } },
  ],
  webServer: { command: "npm run preview -- --host 127.0.0.1 --port 4175 --strictPort", url: "http://127.0.0.1:4175", reuseExistingServer: false },
});
