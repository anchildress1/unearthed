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
		// (03 — the route map; the user's eGRID subregion is labeled as
		// text on their pin here, never drawn as a polygon), H3Density
		// (04 — hex-cluster heatmap), CortexChat (05), Ticker (06).
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

	test('heading levels stay contiguous (h1 → h2 → h3)', async ({ page }) => {
		await mockBackend(page);
		await page.goto('/?m=NWPP');
		await expect(page.getByText('tons of coal shipped from this mine')).toBeVisible({ timeout: 15_000 });

		// axe-core flags `heading-order` when levels skip (e.g. h1 → h3).
		// Hero owns the single `<h1>`; every post-hero section headline is
		// a `<h2>`; PlantReveal's nested "What this mine cost." is the only
		// `<h3>`. Regression here (e.g. dropping a section back to h3 for
		// visual-only reasons) silently breaks screen-reader navigation.
		const levels = await page.evaluate(() =>
			[...document.querySelectorAll('h1, h2, h3, h4, h5, h6')].map(n => n.tagName.toLowerCase())
		);
		expect(levels.filter((l) => l === 'h1')).toHaveLength(1);
		expect(levels.filter((l) => l === 'h2').length).toBeGreaterThanOrEqual(5);
		expect(levels).not.toContain('h4');
	});

	test('H3Density renders a single hex-cluster map frame', async ({ page }) => {
		await mockBackend(page);
		await page.goto('/?m=NWPP');
		await expect(page.getByText('tons of coal shipped from this mine')).toBeVisible({ timeout: 15_000 });

		// N° 04 "The seam" is one editorial section with a single
		// `.map-wrap` — the hex-cluster heatmap framed tight on the
		// "shape of extraction." No eGRID polygon is rendered on either
		// map; the user's subregion surfaces only as text on their pin
		// in the upstream route map. This section must not regress to a
		// second `.map-wrap` that would split focus between two framings.
		const h3Section = page.locator('.section-rail.h3-section');
		await expect(h3Section).toHaveCount(1);
		await expect(h3Section.locator('.map-wrap')).toHaveCount(1);
	});
});
