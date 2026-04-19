import { expect, test } from '@playwright/test';
import { mockBackend } from './fixtures.js';

test.describe('editorial chrome', () => {
	test('every section renders its N° / rule / label rail', async ({ page }) => {
		await mockBackend(page);
		await page.goto('/?m=NWPP');
		await expect(page.getByText('tons of coal shipped from this mine')).toBeVisible({ timeout: 15_000 });

		// The hero owns N° 01 via its own `.hero-chrome`; every post-hero
		// section owns a `.section-rail > .rail-chrome`. Post-trace the page
		// should render five section rails: PlantReveal (02), MapSection
		// (03 — the route map, now also carrying the user's eGRID subregion
		// polygon), H3Density (04 — hex-cluster heatmap), CortexChat (05),
		// Ticker (06).
		const rails = page.locator('.section-rail .rail-chrome');
		const count = await rails.count();
		expect(count).toBe(5);

		// Each rail must carry both a number and a label. Empty chrome is a
		// regression: past bugs rendered the wrapper without the spans.
		const numbers = [];
		for (let i = 0; i < count; i++) {
			const rail = rails.nth(i);
			await expect(rail.locator('.rail-num')).toHaveText(/N°\s*\d+/);
			await expect(rail.locator('.rail-label')).not.toBeEmpty();
			numbers.push((await rail.locator('.rail-num').textContent())?.trim());
		}

		// N° numbering must be contiguous 02 → 06 (Hero is 01 and uses its
		// own chrome). A gap here means a section got renumbered without
		// its siblings being updated — the kind of drift the H3Density
		// consolidation was supposed to prevent.
		expect(numbers).toEqual(['N° 02', 'N° 03', 'N° 04', 'N° 05', 'N° 06']);
	});

	test('H3Density renders a single hex-cluster map frame', async ({ page }) => {
		await mockBackend(page);
		await page.goto('/?m=NWPP');
		await expect(page.getByText('tons of coal shipped from this mine')).toBeVisible({ timeout: 15_000 });

		// N° 04 "The seam" is one editorial section with a single
		// `.map-wrap` — the hex-cluster heatmap framed tight on the
		// "shape of extraction." The eGRID subregion polygon framing
		// now lives upstream on MapSection (N° 03), so this section
		// must not regress to a second `.map-wrap` that would duplicate
		// the polygon rendering or split focus between two framings.
		const h3Section = page.locator('.section-rail.h3-section');
		await expect(h3Section).toHaveCount(1);
		await expect(h3Section.locator('.map-wrap')).toHaveCount(1);
	});
});
