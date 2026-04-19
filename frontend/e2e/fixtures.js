// Shared fixtures for e2e backend mocks. These mirror the real payload
// shapes from /mine-for-me, /emissions/{plant}, and /h3-density so the
// frontend's downstream logic (paragraph dedup, formatters, anchors) has
// enough data to exercise.

export const mineForMeJimBridger = {
	plant: 'Jim Bridger',
	plant_operator: 'PacifiCorp',
	plant_coords: [41.7437, -108.7786],
	plant_capacity_mw: 2442,
	mine: 'Black Thunder',
	mine_state: 'WY',
	mine_county: 'Campbell',
	mine_coords: [43.7247, -105.246],
	mine_type: 'Surface',
	mine_msha_id: '48-00977',
	tons: 3_850_000,
	tons_year: 2024,
	subregion_id: 'NWPP',
	prose: 'Black Thunder, a surface mine in Campbell County Wyoming, is the largest coal mine in the United States by annual tonnage.\n\nIt ships coal via BNSF to the Jim Bridger plant outside Rock Springs, where it is burned to meet electricity demand across the Pacific Northwest grid.\n\nBlack Thunder, a surface mine in Campbell County Wyoming, is the largest coal mine in the United States by annual tonnage.',
};

export const emissionsJimBridger = {
	plant: 'Jim Bridger',
	co2_tons: 8_400_000,
	so2_tons: 7_200,
	nox_tons: 11_400,
	year: 2023,
};

export const h3DensityNWPP = {
	resolution: 4,
	state: 'WY',
	cells: [
		{ h3: '841e26dffffffff', count: 12, centroid: [43.7, -105.2] },
		{ h3: '841e267ffffffff', count: 8, centroid: [43.8, -105.4] },
	],
	summary: 'Coal production in the NWPP subregion clusters tightly in the Powder River Basin of northeast Wyoming.',
};

/**
 * Install mocks for every backend endpoint the page touches. Call this
 * before `page.goto` in tests that need a trace to succeed.
 */
export async function mockBackend(page, {
	mineForMe = mineForMeJimBridger,
	emissions = emissionsJimBridger,
	h3Density = h3DensityNWPP,
} = {}) {
	await page.route('**/mine-for-me', (route) =>
		route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mineForMe) }),
	);
	await page.route(/\/emissions\/.+/, (route) =>
		route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(emissions) }),
	);
	await page.route(/\/h3-density(\?.*)?$/, (route) =>
		route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(h3Density) }),
	);
	await page.route('**/ask', (route) =>
		route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ answer: 'mocked', sql: 'SELECT 1' }) }),
	);
	// Swallow the Google Maps bootstrap script and every Place Details /
	// Autocomplete RPC. The share-URL path doesn't need Places, but Hero
	// always tries to load it on mount and an unmocked 3rd-party request
	// slows every test down to its timeout.
	await page.route(/maps\.googleapis\.com|maps\.gstatic\.com/, (route) =>
		route.fulfill({ status: 200, contentType: 'application/javascript', body: '/* mocked */' }),
	);
	// Local eGRID GeoJSON — not strictly needed for the share-URL path
	// (the trace skips client-side point-in-polygon), but other flows hit
	// it on mount. Return an empty collection to keep the fetch cheap.
	await page.route('**/data/egrid_subregions.geojson', (route) =>
		route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify({ type: 'FeatureCollection', features: [] }),
		}),
	);
}
