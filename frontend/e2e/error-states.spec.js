import { expect, test } from '@playwright/test';

const MAPS_STUB_JS = `
	(function () {
		const g = window.google = window.google || {};
		const m = g.maps = g.maps || {};
		m.importLibrary = () => Promise.resolve({});
		if (typeof m.__ib__ === 'function') m.__ib__();
	})();
`;

async function mockThirdPartyRoutes(page) {
	await page.route(/maps\.googleapis\.com/, (route) =>
		route.fulfill({ status: 200, contentType: 'application/javascript', body: MAPS_STUB_JS }),
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
}

test.describe('error states', () => {
	test('API 500 on /mine-for-me shows error state', async ({ page }) => {
		await page.route('**/mine-for-me', (route) =>
			route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Snowflake down"}' }),
		);
		await mockThirdPartyRoutes(page);
		await page.goto('/?m=SRVC');

		await page.waitForTimeout(2000);

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
		await mockThirdPartyRoutes(page);
		await page.goto('/?m=ZZZZ');

		await page.waitForTimeout(2000);

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
		await mockThirdPartyRoutes(page);

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
		await mockThirdPartyRoutes(page);

		await page.goto("/?m=<script>alert(1)</script>");
		await page.waitForTimeout(500);
		expect(calls).toHaveLength(0);
	});
});
