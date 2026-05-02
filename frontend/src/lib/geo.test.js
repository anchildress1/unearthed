import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	findSubregion,
	hasCoalData,
	requestLocation,
} from './geo.js';

// Square covering roughly the continental US longitude band around Kentucky;
// easy to reason about when verifying point-in-polygon behavior.
const squarePolygon = {
	type: 'Feature',
	properties: { Subregion: 'SRTV' },
	geometry: {
		type: 'Polygon',
		coordinates: [[
			[-90, 35],
			[-80, 35],
			[-80, 40],
			[-90, 40],
			[-90, 35],
		]],
	},
};

// Donut: outer ring minus a hole in the middle. Verifies the ring-parity logic
// — a point inside the hole should report as outside.
const donutPolygon = {
	type: 'Feature',
	properties: { Subregion: 'RFCW' },
	geometry: {
		type: 'Polygon',
		coordinates: [
			[[-100, 30], [-60, 30], [-60, 50], [-100, 50], [-100, 30]],
			[[-85, 38], [-75, 38], [-75, 42], [-85, 42], [-85, 38]],
		],
	},
};

const multiPolygon = {
	type: 'Feature',
	properties: { Subregion: 'NWPP' },
	geometry: {
		type: 'MultiPolygon',
		coordinates: [
			[[[-125, 40], [-115, 40], [-115, 50], [-125, 50], [-125, 40]]],
			[[[-110, 30], [-100, 30], [-100, 35], [-110, 35], [-110, 30]]],
		],
	},
};

describe('findSubregion', () => {
	it('returns subregion id when point is inside a simple polygon', () => {
		const gj = { features: [squarePolygon] };
		expect(findSubregion(37.5, -85, gj)).toBe('SRTV');
	});

	it('returns null when no polygon contains the point', () => {
		const gj = { features: [squarePolygon] };
		expect(findSubregion(0, 0, gj)).toBeNull();
	});

	it('treats hole interiors as outside the polygon', () => {
		const gj = { features: [donutPolygon] };
		// Inside outer ring but inside the hole.
		expect(findSubregion(40, -80, gj)).toBeNull();
		// Inside outer ring, outside the hole.
		expect(findSubregion(32, -90, gj)).toBe('RFCW');
	});

	it('matches any polygon inside a MultiPolygon feature', () => {
		const gj = { features: [multiPolygon] };
		expect(findSubregion(45, -120, gj)).toBe('NWPP');
		expect(findSubregion(32.5, -105, gj)).toBe('NWPP');
		expect(findSubregion(0, 0, gj)).toBeNull();
	});

	it('picks the first matching feature when multiple contain the point', () => {
		const gj = { features: [squarePolygon, donutPolygon] };
		// (37.5, -85) is inside both; first wins.
		expect(findSubregion(37.5, -85, gj)).toBe('SRTV');
	});

	it('handles empty feature collections without throwing', () => {
		expect(findSubregion(37, -85, { features: [] })).toBeNull();
	});
});

describe('hasCoalData', () => {
	it.each([
		['SRTV', true],
		['RFCW', true],
		['NWPP', true],
		['HIOA', false], // Hawaii — not a coal subregion.
		['', false],
		['unknown', false],
	])('hasCoalData(%s) === %s', (id, expected) => {
		expect(hasCoalData(id)).toBe(expected);
	});
});

describe('loadSubregionGeoJSON', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', vi.fn());
	});
	afterEach(() => {
		vi.unstubAllGlobals();
		vi.resetModules();
	});

	it('fetches and caches GeoJSON from the expected path', async () => {
		const payload = { type: 'FeatureCollection', features: [] };
		fetch.mockResolvedValueOnce({ ok: true, json: async () => payload });

		const mod = await import('./geo.js?fresh=1');
		const first = await mod.loadSubregionGeoJSON();
		const second = await mod.loadSubregionGeoJSON();

		expect(fetch).toHaveBeenCalledWith('/data/egrid_subregions.geojson');
		expect(fetch).toHaveBeenCalledTimes(1);
		expect(first).toEqual(payload);
		expect(second).toBe(first);
	});

	it('throws on non-OK response', async () => {
		fetch.mockResolvedValueOnce({ ok: false, status: 404 });
		const mod = await import('./geo.js?fresh=2');
		await expect(mod.loadSubregionGeoJSON()).rejects.toThrow(/Failed to load/);
	});
});

describe('requestLocation', () => {
	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('resolves null when the navigator has no geolocation', async () => {
		vi.stubGlobal('navigator', {});
		await expect(requestLocation()).resolves.toBeNull();
	});

	it('resolves coords on success', async () => {
		const getCurrentPosition = vi.fn((success) =>
			success({ coords: { latitude: 37.5, longitude: -85 } }),
		);
		vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } });
		await expect(requestLocation()).resolves.toEqual({ lat: 37.5, lon: -85 });
	});

	it('resolves null on geolocation error', async () => {
		const getCurrentPosition = vi.fn((_success, error) => error(new Error('denied')));
		vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } });
		await expect(requestLocation()).resolves.toBeNull();
	});
});
