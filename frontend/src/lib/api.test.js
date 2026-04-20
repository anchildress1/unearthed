import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchAsk, fetchEmissions, fetchMineForMe } from './api.js';

function okResponse(body) {
	return { ok: true, status: 200, json: async () => body };
}

function errResponse(status, body = {}) {
	return { ok: false, status, json: async () => body };
}

describe('fetchMineForMe', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', vi.fn());
	});
	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('posts subregion_id as JSON', async () => {
		fetch.mockResolvedValueOnce(okResponse({ plant: 'Jim Bridger' }));
		const result = await fetchMineForMe('NWPP');
		expect(fetch).toHaveBeenCalledWith('/mine-for-me', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ subregion_id: 'NWPP' }),
		});
		expect(result).toEqual({ plant: 'Jim Bridger' });
	});

	it('surfaces server detail on failure', async () => {
		fetch.mockResolvedValueOnce(errResponse(400, { detail: 'no plants in subregion' }));
		await expect(fetchMineForMe('AKGD')).rejects.toThrow('no plants in subregion');
	});

	it('falls back to status code when server JSON is unparseable', async () => {
		fetch.mockResolvedValueOnce({
			ok: false,
			status: 502,
			json: async () => { throw new Error('bad json'); },
		});
		await expect(fetchMineForMe('NWPP')).rejects.toThrow('Failed to load mine data (502)');
	});
});

describe('fetchEmissions', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', vi.fn());
	});
	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('URL-encodes the plant name in the path', async () => {
		fetch.mockResolvedValueOnce(okResponse({ co2_tons: 1 }));
		await fetchEmissions('Black Thunder / PRB');
		expect(fetch).toHaveBeenCalledWith('/emissions/Black%20Thunder%20%2F%20PRB');
	});

	it('throws with status on failure', async () => {
		fetch.mockResolvedValueOnce(errResponse(404));
		await expect(fetchEmissions('Missing')).rejects.toThrow('Failed to load emissions (404)');
	});
});

describe('fetchAsk', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', vi.fn());
	});
	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('sends question and subregion when both provided', async () => {
		fetch.mockResolvedValueOnce(okResponse({ answer: 'hi' }));
		await fetchAsk('how much coal?', 'SRTV');
		expect(fetch).toHaveBeenCalledWith('/ask', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ question: 'how much coal?', subregion_id: 'SRTV' }),
		});
	});

	it('omits subregion_id when null/empty', async () => {
		fetch.mockResolvedValueOnce(okResponse({ answer: 'hi' }));
		await fetchAsk('how much coal?', null);
		const body = JSON.parse(fetch.mock.calls[0][1].body);
		expect(body).toEqual({ question: 'how much coal?' });
	});

	it('prefers detail over error in the failure body', async () => {
		fetch.mockResolvedValueOnce(errResponse(500, { detail: 'cortex down', error: 'other' }));
		await expect(fetchAsk('q')).rejects.toThrow('cortex down');
	});

	it('falls back to error field when no detail', async () => {
		fetch.mockResolvedValueOnce(errResponse(500, { error: 'cortex down' }));
		await expect(fetchAsk('q')).rejects.toThrow('cortex down');
	});
});

describe('fetchH3Density', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', vi.fn());
	});
	afterEach(() => {
		vi.unstubAllGlobals();
		vi.resetModules();
	});

	it('builds query string from resolution and state', async () => {
		fetch.mockResolvedValueOnce(okResponse({ cells: [] }));
		const mod = await import('./api.js?h3=1');
		await mod.fetchH3Density(5, 'WY');
		expect(fetch).toHaveBeenCalledWith('/h3-density?resolution=5&state=WY');
	});

	it('omits state param when not provided', async () => {
		fetch.mockResolvedValueOnce(okResponse({ cells: [] }));
		const mod = await import('./api.js?h3=2');
		await mod.fetchH3Density(4);
		expect(fetch).toHaveBeenCalledWith('/h3-density?resolution=4');
	});

	it('dedupes concurrent calls for the same scope', async () => {
		let resolveFetch;
		fetch.mockImplementationOnce(() => new Promise((r) => { resolveFetch = r; }));
		const mod = await import('./api.js?h3=3');
		const a = mod.fetchH3Density(4, 'WY');
		const b = mod.fetchH3Density(4, 'WY');
		expect(fetch).toHaveBeenCalledTimes(1);
		resolveFetch(okResponse({ cells: [1] }));
		await expect(Promise.all([a, b])).resolves.toEqual([{ cells: [1] }, { cells: [1] }]);
	});

	it('re-fetches a second time after the first promise resolves', async () => {
		fetch.mockResolvedValueOnce(okResponse({ cells: [1] }));
		const mod = await import('./api.js?h3=4');
		await mod.fetchH3Density(4, 'WY');
		fetch.mockResolvedValueOnce(okResponse({ cells: [2] }));
		await mod.fetchH3Density(4, 'WY');
		expect(fetch).toHaveBeenCalledTimes(2);
	});

	it('clears in-flight slot on error so retries can happen', async () => {
		fetch.mockResolvedValueOnce(errResponse(500));
		const mod = await import('./api.js?h3=5');
		await expect(mod.fetchH3Density(4, 'WY')).rejects.toThrow(/Failed to load density/);
		fetch.mockResolvedValueOnce(okResponse({ cells: [] }));
		await expect(mod.fetchH3Density(4, 'WY')).resolves.toEqual({ cells: [] });
	});
});
