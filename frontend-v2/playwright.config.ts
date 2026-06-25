import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright config for P0-7/P0-8 verification.
 *
 * - Uses the Vite dev server (frontend-v2) on port 5183.
 * - Tests stub backend API responses via page.route() so the SPA can
 *   render without the real backend running.
 * - Chromium-only to keep the run cheap.
 */
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: /.*\.spec\.ts$/,
  fullyParallel: false,           // 1 worker — local verification, deterministic
  workers: 1,
  retries: 0,                     // we want first-attempt pass/fail signal
  reporter: [['list']],
  timeout: 120_000,
  expect: {
    timeout: 30_000
  },
  use: {
    baseURL: 'http://127.0.0.1:5183',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 30_000,
    navigationTimeout: 60_000,
    // No viewport override — use defaults so layout (12-col / 1920) renders.
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // The pre-installed browser at chromium-1155 is at chrome-win\chrome.exe
        // (NOT chrome-win64 as Playwright 1.61+ expects). 1.52.0 uses 1155.
        launchOptions: {
          executablePath: 'C:\\Users\\Administrator\\AppData\\Local\\ms-playwright\\chromium-1155\\chrome-win\\chrome.exe'
        }
      }
    }
  ],
  // We start the dev server manually before running tests, so no webServer here.
  // This keeps the dev server lifecycle independent of the test run.
})
