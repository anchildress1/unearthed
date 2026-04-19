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

export async function fetchH3Density(resolution = 4, state = null) {
	const params = new URLSearchParams({ resolution: String(resolution) });
	if (state) params.set('state', state);
	const resp = await fetch(`/h3-density?${params}`);
	if (!resp.ok) {
		throw new Error(`Failed to load density (${resp.status})`);
	}
	return resp.json();
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
