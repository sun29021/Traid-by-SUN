import { defineConfig } from '@playwright/test';

const PORT = Number(process.env.E2E_PORT ?? 8766);

/**
 * End-to-end tests against the production build served by the real backend
 * (ARCHITECTURE.md §15). Uses the installed Google Chrome by default so no browser
 * download is needed; set PW_CHANNEL=chromium after `npx playwright install chromium`.
 */
export default defineConfig({
  testDir: 'e2e',
  fullyParallel: false,
  workers: 1, // tests share one server and one data folder
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    channel: process.env.PW_CHANNEL ?? 'chrome',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run build && node e2e/server.mjs',
    url: `http://127.0.0.1:${PORT}/api/v1/health`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
