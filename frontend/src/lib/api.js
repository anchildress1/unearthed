export async function fetchMineForMe(subregionId) {
	const resp = await fetch('/mine-for-me', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ subregion_id: subregionId }),
	});
	if (!resp.ok) {
		const err = await resp.json().catch(() => ({}));
		throw new Error(err.detail || `Failed to load mine data (${resp.status})`);
	}
	return resp.json();
}

export async function fetchEmissions(plantName) {
	const resp = await fetch(`/emissions/${encodeURIComponent(plantName)}`);
	if (!resp.ok) {
		throw new Error(`Failed to load emissions (${resp.status})`);
	}
	return resp.json();
}

// In-flight request dedupe keyed by (resolution, state). The reveal renders
// H3Density twice — once zoomed to the grid, once zoomed to the coal seam —
// and both mount simultaneously, so a plain fetch would double every
// /h3-density call for the same scope. Resolves to the shared promise if one
// is already pending; successful resolution clears the slot so a later trace
// for the same scope re-fetches fresh.
const _h3Pending = new Map();

export async function fetchH3Density(resolution = 4, state = null) {
	const key = `${resolution}|${state ?? ''}`;
	const pending = _h3Pending.get(key);
	if (pending) return pending;

	const params = new URLSearchParams({ resolution: String(resolution) });
	if (state) params.set('state', state);
	const promise = (async () => {
		try {
			const resp = await fetch(`/h3-density?${params}`);
			if (!resp.ok) {
				throw new Error(`Failed to load density (${resp.status})`);
			}
			return await resp.json();
		} finally {
			_h3Pending.delete(key);
		}
	})();
	_h3Pending.set(key, promise);
	return promise;
}

export async function fetchAsk(question, subregionId) {
	const resp = await fetch('/ask', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ question, subregion_id: subregionId || undefined }),
	});
	if (!resp.ok) {
		const err = await resp.json().catch(() => ({}));
		throw new Error(err.detail || err.error || `Failed to ask question (${resp.status})`);
	}
	return resp.json();
}
