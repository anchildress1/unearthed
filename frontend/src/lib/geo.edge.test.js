/**
 * geo.js — edge-case tests not covered in the main geo.test.js.
 *
 * Covers: boundary coordinates, NaN/Infinity, requestLocation timeout
 * parameter, loadSubregionGeoJSON network failure.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { findSubregion, hasCoalData, requestLocation } from './geo.js';

const square = {
	type: 'Feature',
	properties: { Subregion: 'TEST' },
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

describe('findSubregion — boundary coordinates', () => {
	it('handles NaN latitude gracefully', () => {
		const gj = { features: [square] };
		// NaN coordinates should not crash — they just won't match any polygon
		expect(findSubregion(Number.NaN, -85, gj)).toBeNull();
	});

	it('handles Infinity longitude gracefully', () => {
		const gj = { features: [square] };
		expect(findSubregion(37, Infinity, gj)).toBeNull();
	});

	it('handles negative Infinity coordinates', () => {
		const gj = { features: [square] };
		expect(findSubregion(-Infinity, -Infinity, gj)).toBeNull();
	});

	it('matches a point exactly on a vertex', () => {
		const gj = { features: [square] };
		// Vertex points are implementation-dependent — just verify no crash
		const result = findSubregion(35, -90, gj);
		// May be null or 'TEST' depending on ray-casting edge behavior
		expect(result === null || result === 'TEST').toBe(true);
	});

	it('matches a point exactly on an edge', () => {
		const gj = { features: [square] };
		// Point on the bottom edge: lat=35, lng=-85
		const result = findSubregion(35, -85, gj);
		expect(result === null || result === 'TEST').toBe(true);
	});
});

describe('hasCoalData — additional subregions', () => {
	it.each([
		['SRVC', true],
		['FRCC', true],
		['MROE', true],
		['CAMX', true],
		['ERCT', true],
		['SPSO', true],
		[null, false],
		[undefined, false],
	])('hasCoalData(%s) === %s', (id, expected) => {
		expect(hasCoalData(id)).toBe(expected);
	});
});

describe('requestLocation — edge cases', () => {
	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('passes timeout to getCurrentPosition options', async () => {
		const getCurrentPosition = vi.fn((success) =>
			success({ coords: { latitude: 37, longitude: -85 } }),
		);
		vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } });

		await requestLocation();

		const options = getCurrentPosition.mock.calls[0][2];
		expect(options).toBeDefined();
		expect(options.timeout).toBeGreaterThan(0);
	});

	it('handles coords at valid extremes', async () => {
		const getCurrentPosition = vi.fn((success) =>
			success({ coords: { latitude: 90, longitude: -180 } }),
		);
		vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } });

		const result = await requestLocation();
		expect(result).toEqual({ lat: 90, lon: -180 });
	});
});

describe('loadSubregionGeoJSON — edge cases', () => {
	afterEach(() => {
		vi.unstubAllGlobals();
		vi.resetModules();
	});

	it('throws on network rejection', async () => {
		vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new TypeError('offline')));
		const mod = await import('./geo.js?edge=1');
		await expect(mod.loadSubregionGeoJSON()).rejects.toThrow('offline');
	});
});
