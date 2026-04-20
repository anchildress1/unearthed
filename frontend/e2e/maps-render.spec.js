import { expect, test } from '@playwright/test';
import { installGoogleMapsStub, mockBackend } from './fixtures.js';

// These tests drive MapSection + H3Density through a real `google.maps`
// surface (behavioral doubles, not pixel-perfect) so regressions in
// marker construction, overlay lifecycle, or label placement surface at
// CI time instead of only in production. The existing share-URL / editorial
// specs use the empty `importLibrary → {}` shim in mockBackend and silently
// swallow any map error in the catch block — they never asserted anything
// about map construction because nothing was constructed. This file fills
// that gap.

test.describe('map runtime', () => {
	test('MapSection builds mine + plant anchors and labels on share-URL replay', async ({ page }) => {
		await installGoogleMapsStub(page);
		await mockBackend(page);
		await page.goto('/?m=NWPP');

		await expect(page.getByText('tons of coal shipped from this mine')).toBeVisible({
			timeout: 15_000,
		});

		// MapSection calls `new google.maps.Map` once; H3Density calls it
		// once. Both sections should have booted their maps.
		const mapsCount = await page.evaluate(() => window.__gmapsCalls.maps.length);
		expect(mapsCount).toBeGreaterThanOrEqual(2);

		// Share URL trace has no user_coords in the payload, so MapSection
		// creates two anchor Markers (mine + plant). H3Density creates one
		// anchor Marker (mine) plus one Marker per hex cell. The fixture
		// payload has 2 hex cells, so 2 + 1 + 2 = 5 minimum. Assert on the
		// floor so adding hex cells to fixtures doesn't flake the test.
		const markers = await page.evaluate(() => window.__gmapsCalls.markers);
		expect(markers.length).toBeGreaterThanOrEqual(5);

		// Every Marker must carry a `title` — axe-core's aria-command-name
		// rule is why we made `title` required on anchorMarker, and this
		// test guards against accidental reverts.
		for (const m of markers) {
			expect(m.title, `marker title missing: ${JSON.stringify(m)}`).toBeTruthy();
		}

		// MapSection's anchors should carry the editorial-style titles
		// ("Coal mine: X" / "Power plant: X"). The hex markers use a
		// different format (`N coal mines in this area …`).
		const anchorTitles = markers.map((m) => m.title);
		expect(anchorTitles.some((t) => t.startsWith('Coal mine: '))).toBe(true);
		expect(anchorTitles.some((t) => t.startsWith('Power plant: '))).toBe(true);
	});

	test('OverlayView lifecycle drives label cards onto the map', async ({ page }) => {
		await installGoogleMapsStub(page);
		await mockBackend(page);
		await page.goto('/?m=NWPP');

		await expect(page.getByText('tons of coal shipped from this mine')).toBeVisible({
			timeout: 15_000,
		});

		// Wait for MapSection's async attachLabels chain (idle → projection
		// probe → createLabeledMarker) to run. The projection probe alone
		// contributes an OverlayView instance; the flow overlay and each
		// label card add more. At least 3 (flow + 2 labels) should exist
		// after MapSection settles, plus H3Density's mine-anchor label.
		await page.waitForFunction(
			() => window.__gmapsCalls.overlays.length >= 4,
			undefined,
			{ timeout: 10_000 },
		);

		// Label cards are rendered into the panes host set up by the stub.
		// Guards the PinCardOverlay.onAdd → floatPane.appendChild path:
		// if a regression breaks card creation, this count goes to zero.
		const cardsInHost = await page.evaluate(() => {
			const host = document.getElementById('__gmaps_stub_panes');
			return host ? host.children.length : 0;
		});
		expect(cardsInHost).toBeGreaterThanOrEqual(3);
	});

	test('projection probe resolves via draw() callback, not synchronous getProjection', async ({ page }) => {
		await installGoogleMapsStub(page);
		await mockBackend(page);

		// Listen for the "label placement failed" console error that only
		// fires if projectAnchors throws or times out. Regressing the P2
		// fix (synchronous getProjection returning null → bailing out)
		// would surface here even though the test doesn't query labels
		// directly: the stub's OverlayView.setMap defers onAdd/draw to a
		// microtask, so a naive getProjection() call right after setMap
		// returns null and attachLabels would skip silently without this
		// assertion.
		const errors = [];
		page.on('console', (msg) => {
			if (msg.type() === 'error' && msg.text().includes('label placement failed')) {
				errors.push(msg.text());
			}
		});

		await page.goto('/?m=NWPP');
		await expect(page.getByText('tons of coal shipped from this mine')).toBeVisible({
			timeout: 15_000,
		});
		// Give any queued microtask-based failures a chance to fire before
		// asserting. 200ms is well past any projection draw cycle.
		await page.waitForTimeout(200);
		expect(errors).toEqual([]);
	});
});
