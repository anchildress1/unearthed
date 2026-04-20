/**
 * api.js — edge-case and error-path tests not covered in the main api.test.js.
 *
 * Covers: network failures (fetch throws), timeout-like scenarios,
 * empty/null response bodies, H3 dedupe with different scopes.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

describe('fetchMineForMe — network errors', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', vi.fn());
	});
	afterEach(() => {
		vi.unstubAllGlobals();
		vi.resetModules();
	});

	it('throws on fetch rejection (network offline)', async () => {
		fetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));
		const { fetchMineForMe } = await import('./api.js?edge=1');
		await expect(fetchMineForMe('SRVC')).rejects.toThrow('Failed to fetch');
	});

	it('handles response with empty body gracefully', async () => {
		fetch.mockResolvedValueOnce({
			ok: false,
			status: 500,
			text: async () => '',
			json: async () => {
				throw new Error('no body');
			},
		});
		const { fetchMineForMe } = await import('./api.js?edge=2');
		await expect(fetchMineForMe('SRVC')).rejects.toThrow('500');
	});
});

describe('fetchEmissions — network errors', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', vi.fn());
	});
	afterEach(() => {
		vi.unstubAllGlobals();
		vi.resetModules();
	});

	it('throws on fetch rejection', async () => {
		fetch.mockRejectedValueOnce(new TypeError('network error'));
		const { fetchEmissions } = await import('./api.js?edge=3');
		await expect(fetchEmissions('Cross')).rejects.toThrow('network error');
	});
});

describe('fetchAsk — edge cases', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', vi.fn());
	});
	afterEach(() => {
		vi.unstubAllGlobals();
		vi.resetModules();
	});

	it('throws on fetch rejection', async () => {
		fetch.mockRejectedValueOnce(new TypeError('offline'));
		const { fetchAsk } = await import('./api.js?edge=4');
		await expect(fetchAsk('q')).rejects.toThrow('offline');
	});

	it('omits subregion_id when empty string', async () => {
		fetch.mockResolvedValueOnce({
			ok: true,
			status: 200,
			json: async () => ({ answer: 'ok' }),
		});
		const { fetchAsk } = await import('./api.js?edge=5');
		await fetchAsk('How much?', '');
		const body = JSON.parse(fetch.mock.calls[0][1].body);
		// Empty string is falsy → subregion_id omitted via || undefined
		expect(body).not.toHaveProperty('subregion_id');
	});

	it('includes subregion_id when provided', async () => {
		fetch.mockResolvedValueOnce({
			ok: true,
			status: 200,
			json: async () => ({ answer: 'ok' }),
		});
		const { fetchAsk } = await import('./api.js?edge=6');
		await fetchAsk('How much?', 'SRVC');
		const body = JSON.parse(fetch.mock.calls[0][1].body);
		expect(body.subregion_id).toBe('SRVC');
	});
});

describe('fetchH3Density — scope isolation', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', vi.fn());
	});
	afterEach(() => {
		vi.unstubAllGlobals();
		vi.resetModules();
	});

	it('treats different resolutions as different scopes', async () => {
		fetch.mockResolvedValue({
			ok: true,
			status: 200,
			json: async () => ({ cells: [] }),
		});
		const mod = await import('./api.js?edge=7');
		await Promise.all([mod.fetchH3Density(4, 'WV'), mod.fetchH3Density(5, 'WV')]);
		expect(fetch).toHaveBeenCalledTimes(2);
	});

	it('treats different states as different scopes', async () => {
		fetch.mockResolvedValue({
			ok: true,
			status: 200,
			json: async () => ({ cells: [] }),
		});
		const mod = await import('./api.js?edge=8');
		await Promise.all([mod.fetchH3Density(4, 'WV'), mod.fetchH3Density(4, 'PA')]);
		expect(fetch).toHaveBeenCalledTimes(2);
	});

	it('treats null state and undefined state as the same scope', async () => {
		let resolvers = [];
		fetch.mockImplementation(
			() => new Promise((r) => resolvers.push(r)),
		);
		const mod = await import('./api.js?edge=9');
		const a = mod.fetchH3Density(4, null);
		const b = mod.fetchH3Density(4, undefined);
		// Both map to key "4|" — should share the same fetch
		expect(fetch).toHaveBeenCalledTimes(1);
		resolvers[0]({
			ok: true,
			status: 200,
			json: async () => ({ cells: [] }),
		});
		await Promise.all([a, b]);
	});
});
