// Shared fixtures for e2e backend mocks. These mirror the real payload
// shapes from /mine-for-me, /emissions/{plant}, and /h3-density so the
// frontend's downstream logic (paragraph dedup, formatters, anchors) has
// enough data to exercise.

// Fields mirror MineForMeResponse in app/models.py — including the three
// MSHA safety stats surfaced in PlantReveal's cost block. Keep this in
// sync when the backend payload changes; an out-of-date fixture masks
// regressions in subtitle rendering (mine_id → MSHA card) and the
// people-subsection layout (fatalities / injuries / days-lost rows).
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
	mine_id: '4800977',
	tons: 3_850_000,
	tons_year: 2024,
	subregion_id: 'NWPP',
	fatalities: 0,
	injuries_lost_time: 0,
	days_lost: 0,
	prose: 'Black Thunder, a surface mine in Campbell County Wyoming, is the largest coal mine in the United States by annual tonnage.\n\nIt ships coal via BNSF to the Jim Bridger plant outside Rock Springs, where it is burned to meet electricity demand across the Pacific Northwest grid.\n\nBlack Thunder, a surface mine in Campbell County Wyoming, is the largest coal mine in the United States by annual tonnage.',
};

export const emissionsJimBridger = {
	plant: 'Jim Bridger',
	co2_tons: 8_400_000,
	so2_tons: 7_200,
	nox_tons: 11_400,
	year: 2023,
};

// Mirrors the /h3-density response shape from app/main.py:269-276.
// Cells come out of Snowflake with `h3` / `lat` / `lng` / `total` /
// `active` / `abandoned`, and the envelope also carries `totals` and
// `summary_degraded`. An out-of-date fixture lets density-plotting logic
// (H3Density.svelte's filteredCells, totalRange, renderHexes) render on
// the wrong keys and pass the suite without exercising the real render
// path — earlier revisions of this fixture used `count` / `centroid` and
// silently masked schema drift.
export const h3DensityNWPP = {
	resolution: 4,
	state: 'WY',
	cells: [
		{ h3: '841e26dffffffff', lat: 43.7, lng: -105.2, total: 12, active: 3, abandoned: 9 },
		{ h3: '841e267ffffffff', lat: 43.8, lng: -105.4, total: 8, active: 2, abandoned: 6 },
	],
	totals: { total: 20, active: 5, abandoned: 15 },
	summary: 'Coal production in the NWPP subregion clusters tightly in the Powder River Basin of northeast Wyoming.',
	summary_degraded: false,
};

/**
 * Install a behavioral double of the `google.maps` namespace into the page
 * before any app script runs. Unlike the empty `importLibrary → {}` shim
 * (below in `mockBackend`), this stub exposes real constructor classes for
 * `Map`, `Marker`, `OverlayView`, `LatLng`, `LatLngBounds`, `InfoWindow`,
 * plus `event` and `geometry.spherical.interpolate` — enough surface area
 * for MapSection + H3Density to run end-to-end. Every construction is
 * recorded on `window.__gmapsCalls` so tests can assert that the right
 * markers, overlays, and listeners actually got created.
 *
 * The stub:
 *   - Fires `idle` on a microtask after `fitBounds` so attachLabels'
 *     addListenerOnce('idle') callback runs deterministically.
 *   - Calls OverlayView.onAdd + draw on a microtask after `setMap(map)`
 *     so the new projection-probe promise resolves immediately after
 *     setMap (exercising the draw-callback path the P2 fix introduced).
 *   - Returns `{ AutocompleteSessionToken, AutocompleteSuggestion }`
 *     stubs for 'places' so Hero's onMount doesn't throw on load — the
 *     no-op `fetchAutocompleteSuggestions` keeps the input idle unless a
 *     test explicitly types into it.
 *
 * Call before `mockBackend` (or before `page.goto`) so `addInitScript`
 * runs first; once `google.maps.importLibrary` is installed, maps.js's
 * loadGoogleMaps() short-circuits without fetching the real script.
 */
export async function installGoogleMapsStub(page) {
	await page.addInitScript(() => {
		const calls = {
			maps: [],
			markers: [],
			overlays: [],
			infoWindows: [],
			labels: 0,
		};
		Object.defineProperty(globalThis, '__gmapsCalls', { value: calls, writable: false });

		class LatLng {
			constructor(lat, lng) {
				this._lat = typeof lat === 'object' ? lat.lat : lat;
				this._lng = typeof lat === 'object' ? lat.lng : lng;
			}
			lat() { return this._lat; }
			lng() { return this._lng; }
		}
		class LatLngBounds {
			constructor() { this.points = []; }
			extend(p) {
				const lat = typeof p.lat === 'function' ? p.lat() : p.lat;
				const lng = typeof p.lng === 'function' ? p.lng() : p.lng;
				this.points.push({ lat, lng });
				return this;
			}
		}
		const event = {
			addListener(obj, type, fn) {
				if (!obj.__listeners) obj.__listeners = {};
				if (!obj.__listeners[type]) obj.__listeners[type] = [];
				obj.__listeners[type].push(fn);
				return { remove: () => {} };
			},
			addListenerOnce(obj, type, fn) {
				const wrapped = (...args) => {
					const arr = obj.__listeners?.[type];
					if (arr) {
						const i = arr.indexOf(wrapped);
						if (i >= 0) arr.splice(i, 1);
					}
					fn(...args);
				};
				return event.addListener(obj, type, wrapped);
			},
		};
		class MapDouble {
			constructor(el, opts) {
				this.el = el;
				this.opts = opts;
				calls.maps.push({ el, opts });
			}
			fitBounds(bounds, padding) {
				this.lastBounds = bounds;
				this.lastPadding = padding;
				// Fire idle on a microtask so addListenerOnce(map, 'idle', fn)
				// runs after the caller returns — mirrors the real SDK.
				queueMicrotask(() => {
					const arr = this.__listeners?.idle?.slice();
					if (arr) for (const fn of arr) fn();
				});
			}
		}
		class MarkerDouble {
			constructor(opts) {
				this.opts = opts;
				this._pos = opts.position;
				calls.markers.push(opts);
			}
			setMap(m) { this.map = m; }
			getPosition() { return new LatLng(this._pos.lat, this._pos.lng); }
			addListener() { return { remove: () => {} }; }
		}
		class InfoWindowDouble {
			constructor(opts) { this.opts = opts; calls.infoWindows.push(opts); }
			setContent(c) { this.content = c; }
			open() { this.isOpen = true; }
			close() { this.isOpen = false; }
		}
		class OverlayViewDouble {
			_map = null;
			constructor() { calls.overlays.push(this); }
			setMap(m) {
				const prev = this._map;
				this._map = m;
				if (m && !prev) {
					queueMicrotask(() => {
						this.onAdd?.();
						this.draw?.();
					});
				} else if (!m && prev) {
					queueMicrotask(() => this.onRemove?.());
				}
			}
			getProjection() {
				if (!this._map) return null;
				return {
					// Linear scaling is fine — the only caller (MapSection's
					// projectAnchors) just needs a stable lat/lng → pixel map
					// so relative ordering (above/below/side) is deterministic.
					fromLatLngToDivPixel(latLng) {
						const lat = typeof latLng.lat === 'function' ? latLng.lat() : latLng.lat;
						const lng = typeof latLng.lng === 'function' ? latLng.lng() : latLng.lng;
						return { x: lng * 100, y: -lat * 100 };
					},
				};
			}
			getPanes() {
				// Real panes aren't pixel-accurate here; we just need somewhere
				// for PinCardOverlay.onAdd to appendChild() without throwing.
				// A dedicated container makes it easy for tests to count cards.
				let host = document.getElementById('__gmaps_stub_panes');
				if (!host) {
					host = document.createElement('div');
					host.id = '__gmaps_stub_panes';
					host.style.display = 'none';
					document.body.appendChild(host);
				}
				return { floatPane: host, overlayLayer: host, mapPane: host, markerLayer: host, overlayMouseTarget: host };
			}
		}
		const geometry = {
			spherical: {
				interpolate(a, b, t) {
					const aLat = typeof a.lat === 'function' ? a.lat() : a.lat;
					const aLng = typeof a.lng === 'function' ? a.lng() : a.lng;
					const bLat = typeof b.lat === 'function' ? b.lat() : b.lat;
					const bLng = typeof b.lng === 'function' ? b.lng() : b.lng;
					return new LatLng(aLat + (bLat - aLat) * t, aLng + (bLng - aLng) * t);
				},
			},
		};
		const SymbolPath = { CIRCLE: 0, FORWARD_CLOSED_ARROW: 1, BACKWARD_CLOSED_ARROW: 2 };

		// Minimal Places surface so Hero's `placesLib = await
		// importLibrary('places')` succeeds. fetchAutocompleteSuggestions
		// returns nothing so the suggestion dropdown stays empty unless a
		// test wants to stub AutocompleteSuggestion explicitly.
		const places = {
			AutocompleteSessionToken: class AutocompleteSessionToken { token = null; },
			AutocompleteSuggestion: {
				async fetchAutocompleteSuggestions() { return { suggestions: [] }; },
			},
		};

		const mapsLib = {
			Map: MapDouble,
			Marker: MarkerDouble,
			LatLng,
			LatLngBounds,
			InfoWindow: InfoWindowDouble,
			OverlayView: OverlayViewDouble,
			SymbolPath,
			event,
		};

		if (!globalThis.google) globalThis.google = {};
		const g = globalThis.google;
		g.maps = {
			...mapsLib,
			geometry,
			places,
			importLibrary: async (name) => {
				if (name === 'maps') return mapsLib;
				if (name === 'geometry') return geometry;
				if (name === 'places') return places;
				return {};
			},
		};
	});
}

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
	//
	// The shim matches maps.js's `installImportLibraryShim` contract: the
	// first importLibrary() call triggers a script fetch that, on load,
	// invokes `google.maps.__ib__` (the callback baked into the URL) to
	// resolve the pending promise. We mirror that here so awaited
	// importLibrary() calls in Hero/MapSection/H3Density don't hang — the
	// returned stub script, when executed as a tag, re-installs a trivial
	// importLibrary that resolves to an empty module and fires __ib__.
	await page.route(/maps\.googleapis\.com\/maps\/api\/js/, (route) =>
		route.fulfill({
			status: 200,
			contentType: 'application/javascript',
			body: `
				(function () {
					const g = window.google = window.google || {};
					const m = g.maps = g.maps || {};
					m.importLibrary = () => Promise.resolve({});
					if (typeof m.__ib__ === 'function') m.__ib__();
				})();
			`,
		}),
	);
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
