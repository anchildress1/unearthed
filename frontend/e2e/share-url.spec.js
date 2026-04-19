import { expect, test } from '@playwright/test';
import { mockBackend } from './fixtures.js';

test.describe('share URL replay', () => {
	test('?m=NWPP renders the trace without user interaction', async ({ page }) => {
		await mockBackend(page);
		await page.goto('/?m=NWPP');
		// The "tons shipped" card is the most distinctive anchor in the
		// trace payload — the prose and Cortex chips both mention the mine
		// name, so a raw name match would violate strict mode.
		await expect(page.getByText('tons of coal shipped from this mine')).toBeVisible({ timeout: 15_000 });
		await expect(page.getByText('3,850,000')).toBeVisible();
	});

	test('lowercase subregion is uppercased and replayed', async ({ page }) => {
		let seen;
		// mockBackend registers its own /mine-for-me handler; register our
		// capture *after* it so Playwright (which matches most-recent-first)
		// picks up ours. Fall through to the default payload shape.
		await mockBackend(page);
		await page.route('**/mine-for-me', async (route, request) => {
			seen = JSON.parse(request.postData() ?? '{}').subregion_id;
			await route.fulfill({
				status: 200,
				contentType: 'application/json',
				body: JSON.stringify({
					plant: 'Jim Bridger',
					plant_operator: 'PacifiCorp',
					plant_coords: [41.7, -108.8],
					mine: 'Black Thunder',
					mine_state: 'WY',
					mine_county: 'Campbell',
					mine_coords: [43.7, -105.2],
					mine_type: 'Surface',
					tons: 1_000_000,
					tons_year: 2024,
					subregion_id: 'NWPP',
					prose: 'ok',
				}),
			});
		});
		await page.goto('/?m=nwpp');
		await expect(page.getByText('tons of coal shipped from this mine')).toBeVisible({ timeout: 15_000 });
		expect(seen).toBe('NWPP');
	});

	test('invalid share-URL token is ignored', async ({ page }) => {
		const calls = [];
		await page.route('**/mine-for-me', async (route) => {
			calls.push(route.request().url());
			await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
		});
		await page.goto('/?m=not-a-valid-id!!');
		// Give the page a beat to ever consider making the call.
		await page.waitForTimeout(500);
		expect(calls).toHaveLength(0);
	});
});
