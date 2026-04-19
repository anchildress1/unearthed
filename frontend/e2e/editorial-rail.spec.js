import { expect, test } from '@playwright/test';
import { mockBackend } from './fixtures.js';

test.describe('editorial chrome', () => {
	test('every section renders its N° / rule / label rail', async ({ page }) => {
		await mockBackend(page);
		await page.goto('/?m=NWPP');
		await expect(page.getByText('tons of coal shipped from this mine')).toBeVisible({ timeout: 15_000 });

		// The hero owns N° 01 via its own `.hero-chrome`; every post-hero
		// section owns a `.section-rail > .rail-chrome`. Require at least
		// four rails after trace (PlantReveal, Map, H3 grid, H3 seam, Cortex,
		// Ticker all use SectionRail — but MapSection may not; verify the
		// concrete minimum we're shipping).
		const rails = page.locator('.section-rail .rail-chrome');
		const count = await rails.count();
		expect(count).toBeGreaterThanOrEqual(4);

		// Each rail must carry both a number and a label. Empty chrome is a
		// regression: past bugs rendered the wrapper without the spans.
		for (let i = 0; i < count; i++) {
			const rail = rails.nth(i);
			await expect(rail.locator('.rail-num')).toHaveText(/N°\s*\d+/);
			await expect(rail.locator('.rail-label')).not.toBeEmpty();
		}
	});
});
