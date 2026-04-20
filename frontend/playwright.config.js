import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests run against the built preview server by default so we're
 * exercising the same bundle Lighthouse audits. The backend API is mocked at
 * the `page.route` layer per-test (`/mine-for-me`, `/emissions/*`, etc.) so
 * the suite runs without FastAPI or Snowflake.
 */
export default defineConfig({
	testDir: './e2e',
	fullyParallel: true,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 2 : 0,
	workers: process.env.CI ? 1 : undefined,
	reporter: 'list',
	use: {
		baseURL: 'http://localhost:4173',
		trace: 'on-first-retry',
	},
	projects: [
		{ name: 'chromium', use: { ...devices['Desktop Chrome'] } },
	],
	webServer: {
		command: 'pnpm build && pnpm preview --port 4173',
		url: 'http://localhost:4173',
		reuseExistingServer: !process.env.CI,
		timeout: 180_000,
	},
});
