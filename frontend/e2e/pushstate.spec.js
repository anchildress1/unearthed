import { expect, test } from '@playwright/test';
import { mockBackend } from './fixtures.js';

test.describe('pushState URL preservation', () => {
	test('refreshing after a trace keeps the results visible', async ({ page }) => {
		await mockBackend(page);

		// Simulate a trace by calling the page's onTrace path indirectly via
		// a direct share URL — equivalent state, without needing the real
		// Google Maps Places widget in a browser test.
		await page.goto('/?m=NWPP');
		await expect(page.getByText('tons of coal shipped from this mine')).toBeVisible({ timeout: 15_000 });

		// Reload — URL is already ?m=NWPP, so onMount's replay path should
		// redraw the same page without user input.
		await page.reload();
		await expect(page.getByText('tons of coal shipped from this mine')).toBeVisible({ timeout: 15_000 });
		expect(new URL(page.url()).searchParams.get('m')).toBe('NWPP');
	});
});
