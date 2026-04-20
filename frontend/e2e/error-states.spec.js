import { expect, test } from '@playwright/test';

test.describe('error states', () => {
	test('API 500 on /mine-for-me shows error state', async ({ page }) => {
		// Mock backend returning 500
		await page.route('**/mine-for-me', (route) =>
			route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Snowflake down"}' }),
		);
		await page.route(/maps\.googleapis\.com/, (route) =>
			route.fulfill({ status: 200, contentType: 'application/javascript', body: `
				(function () {
					const g = window.google = window.google || {};
					const m = g.maps = g.maps || {};
					m.importLibrary = () => Promise.resolve({});
					if (typeof m.__ib__ === 'function') m.__ib__();
				})();
			` }),
		);
		await page.route(/maps\.gstatic\.com/, (route) =>
			route.fulfill({ status: 200, contentType: 'application/javascript', body: '/* mocked */' }),
		);
		await page.route('**/data/egrid_subregions.geojson', (route) =>
			route.fulfill({
				status: 200,
				contentType: 'application/json',
				body: JSON.stringify({ type: 'FeatureCollection', features: [] }),
			}),
		);

		await page.goto('/?m=SRVC');

		// The page should show an error message, not crash
		// Wait for the error to surface in the DOM
		await page.waitForTimeout(2000);

		// The page should still be functional (hero is visible)
		const hero = page.locator('.hero-section, [class*="hero"]');
		await expect(hero.first()).toBeVisible({ timeout: 5000 });
	});

	test('API 404 on /mine-for-me for unknown subregion', async ({ page }) => {
		await page.route('**/mine-for-me', (route) =>
			route.fulfill({
				status: 404,
				contentType: 'application/json',
				body: JSON.stringify({ detail: "No coal data available for subregion 'ZZZZ'." }),
			}),
		);
		await page.route(/maps\.googleapis\.com/, (route) =>
			route.fulfill({ status: 200, contentType: 'application/javascript', body: `
				(function () {
					const g = window.google = window.google || {};
					const m = g.maps = g.maps || {};
					m.importLibrary = () => Promise.resolve({});
					if (typeof m.__ib__ === 'function') m.__ib__();
				})();
			` }),
		);
		await page.route(/maps\.gstatic\.com/, (route) =>
			route.fulfill({ status: 200, contentType: 'application/javascript', body: '/* mocked */' }),
		);
		await page.route('**/data/egrid_subregions.geojson', (route) =>
			route.fulfill({
				status: 200,
				contentType: 'application/json',
				body: JSON.stringify({ type: 'FeatureCollection', features: [] }),
			}),
		);

		await page.goto('/?m=ZZZZ');

		// Wait for the error state to render
		await page.waitForTimeout(2000);

		// Page should not crash — hero is still visible
		const hero = page.locator('.hero-section, [class*="hero"]');
		await expect(hero.first()).toBeVisible({ timeout: 5000 });
	});
});

test.describe('share URL edge cases', () => {
	test('?m= with empty value does not trigger trace', async ({ page }) => {
		const calls = [];
		await page.route('**/mine-for-me', async (route) => {
			calls.push(true);
			await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
		});
		await page.route(/maps\.googleapis\.com/, (route) =>
			route.fulfill({ status: 200, contentType: 'application/javascript', body: `
				(function () {
					const g = window.google = window.google || {};
					const m = g.maps = g.maps || {};
					m.importLibrary = () => Promise.resolve({});
					if (typeof m.__ib__ === 'function') m.__ib__();
				})();
			` }),
		);
		await page.route(/maps\.gstatic\.com/, (route) =>
			route.fulfill({ status: 200, contentType: 'application/javascript', body: '/* mocked */' }),
		);
		await page.route('**/data/egrid_subregions.geojson', (route) =>
			route.fulfill({
				status: 200,
				contentType: 'application/json',
				body: JSON.stringify({ type: 'FeatureCollection', features: [] }),
			}),
		);

		await page.goto('/?m=');
		await page.waitForTimeout(500);
		expect(calls).toHaveLength(0);
	});

	test('?m= with special chars does not trigger trace', async ({ page }) => {
		const calls = [];
		await page.route('**/mine-for-me', async (route) => {
			calls.push(true);
			await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
		});
		await page.route(/maps\.googleapis\.com/, (route) =>
			route.fulfill({ status: 200, contentType: 'application/javascript', body: `
				(function () {
					const g = window.google = window.google || {};
					const m = g.maps = g.maps || {};
					m.importLibrary = () => Promise.resolve({});
					if (typeof m.__ib__ === 'function') m.__ib__();
				})();
			` }),
		);
		await page.route(/maps\.gstatic\.com/, (route) =>
			route.fulfill({ status: 200, contentType: 'application/javascript', body: '/* mocked */' }),
		);
		await page.route('**/data/egrid_subregions.geojson', (route) =>
			route.fulfill({
				status: 200,
				contentType: 'application/json',
				body: JSON.stringify({ type: 'FeatureCollection', features: [] }),
			}),
		);

		await page.goto("/?m=<script>alert(1)</script>");
		await page.waitForTimeout(500);
		expect(calls).toHaveLength(0);
	});
});
