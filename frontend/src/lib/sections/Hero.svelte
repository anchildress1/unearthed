<script>
	import {
		geocodeAddress,
		loadSubregionGeoJSON,
		findSubregion,
		hasCoalData,
		requestLocation,
		subregionForState,
		STATE_TO_SUBREGION,
	} from '$lib/geo.js';

	let { loading, error, onTrace } = $props();
	let address = $state('');
	let showStatePicker = $state(false);
	let selectedState = $state('');
	let localError = $state(null);

	const states = Object.keys(STATE_TO_SUBREGION).sort();
	const stateLabels = {
		AL:'Alabama',AK:'Alaska',AZ:'Arizona',AR:'Arkansas',CA:'California',
		CO:'Colorado',CT:'Connecticut',DE:'Delaware',DC:'District of Columbia',
		FL:'Florida',GA:'Georgia',HI:'Hawaii',ID:'Idaho',IL:'Illinois',
		IN:'Indiana',IA:'Iowa',KS:'Kansas',KY:'Kentucky',LA:'Louisiana',
		ME:'Maine',MD:'Maryland',MA:'Massachusetts',MI:'Michigan',MN:'Minnesota',
		MS:'Mississippi',MO:'Missouri',MT:'Montana',NE:'Nebraska',NV:'Nevada',
		NH:'New Hampshire',NJ:'New Jersey',NM:'New Mexico',NY:'New York',
		NC:'North Carolina',ND:'North Dakota',OH:'Ohio',OK:'Oklahoma',
		OR:'Oregon',PA:'Pennsylvania',RI:'Rhode Island',SC:'South Carolina',
		SD:'South Dakota',TN:'Tennessee',TX:'Texas',UT:'Utah',VT:'Vermont',
		VA:'Virginia',WA:'Washington',WV:'West Virginia',WI:'Wisconsin',WY:'Wyoming',
	};

	async function resolveSubregion(lat, lon) {
		const geojson = await loadSubregionGeoJSON();
		const subregion = findSubregion(lat, lon, geojson);
		if (!subregion) {
			localError = 'That location is outside the US grid coverage area.';
			showStatePicker = true;
			return;
		}
		if (!hasCoalData(subregion)) {
			localError = `Your grid subregion (${subregion}) has no active coal supply chain.`;
			showStatePicker = true;
			return;
		}
		onTrace(subregion, { lat, lon });
	}

	async function handleSubmit(e) {
		e.preventDefault();
		if (!address.trim()) return;
		localError = null;
		const coords = await geocodeAddress(address.trim());
		if (!coords) {
			localError = 'Could not find that location. Try a full address or zip code.';
			return;
		}
		await resolveSubregion(coords.lat, coords.lon);
	}

	async function handleGeolocate() {
		localError = null;
		const coords = await requestLocation();
		if (!coords) {
			localError = 'Location access denied.';
			showStatePicker = true;
			return;
		}
		await resolveSubregion(coords.lat, coords.lon);
	}

	function handleStateGo() {
		if (!selectedState) return;
		const sub = subregionForState(selectedState);
		if (!sub || !hasCoalData(sub)) {
			localError = `No coal data for ${stateLabels[selectedState]}.`;
			return;
		}
		onTrace(sub);
	}
</script>

<section class="hero" aria-label="Find your mine">
	<div class="hero-inner">
		<h1>
			You <span class="rust">came</span> home.<br/>
			You turned <span class="rust">on</span> <em>a light.</em>
		</h1>

		<p class="sub">tell us where that light is</p>

		<div class="input-group glass">
			<form class="form" onsubmit={handleSubmit}>
				<input
					id="address"
					name="address"
					type="text"
					placeholder="Enter address or zip code"
					aria-label="Enter address or zip code"
					bind:value={address}
					maxlength="200"
					autocomplete="off"
					disabled={loading}
				/>
				<button type="submit" disabled={loading}>
					{loading ? '...' : 'trace →'}
				</button>
			</form>

			<div class="divider"><span>or</span></div>

			<button class="geo-btn" onclick={handleGeolocate} disabled={loading}>
				Use my location
			</button>

			{#if showStatePicker}
				<div class="state-pick">
					<select bind:value={selectedState}>
						<option value="">Select a state...</option>
						{#each states as code}
							<option value={code}>{stateLabels[code] || code}</option>
						{/each}
					</select>
					<button onclick={handleStateGo} disabled={!selectedState || loading}>Show me</button>
				</div>
			{/if}
		</div>

		{#if localError || error}
			<p class="err">{localError || error}</p>
		{/if}

		{#if loading}
			<p class="loading">Following the wire back…</p>
		{/if}

		<p class="hint">We find the nearest coal-burning power plant on your grid — nothing is stored or shared.</p>
	</div>

	<a class="credit" href="https://www.flickr.com/photos/nationalmemorialforthemountains/255887679/" target="_blank" rel="noopener">
		Photo: Kent Kessinger / iLoveMountains.org — Flight courtesy SouthWings
	</a>
</section>

<style>
	.hero {
		min-height: 100vh;
		display: flex;
		align-items: center;
		padding: var(--section-pad);
		position: relative;
	}

	.hero-inner {
		max-width: 720px;
	}

	h1 {
		font-family: var(--serif);
		font-size: clamp(3rem, 8vw, 5.8rem);
		font-weight: 400;
		line-height: 1.05;
		color: var(--text);
		margin-bottom: 2.5rem;
		letter-spacing: -0.01em;
	}
	h1 em {
		font-style: italic;
		color: var(--text);
	}
	:global(.rust) {
		color: var(--accent);
	}

	.sub {
		font-family: var(--mono);
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.18em;
		color: var(--text-dim);
		margin-bottom: 1.2rem;
	}

	/* ---- Glass input group ---- */
	.input-group {
		padding: 1.5rem;
		max-width: 460px;
	}

	.form {
		display: flex;
		gap: 0.5rem;
	}

	input[type="text"] {
		flex: 1;
		font-family: var(--serif);
		font-size: 0.95rem;
		padding: 0.8rem 1rem;
		background: rgba(0, 0, 0, 0.4);
		color: var(--text);
		border: 1px solid rgba(255, 255, 255, 0.06);
		border-radius: 6px;
		outline: none;
	}
	input[type="text"]:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 1px var(--accent-glow);
	}
	input[type="text"]::placeholder {
		color: var(--text-ghost);
		font-style: italic;
	}

	button {
		font-family: var(--mono);
		font-size: 0.75rem;
		padding: 0.8rem 1.2rem;
		background: transparent;
		color: var(--accent);
		border: 1px solid rgba(194, 84, 45, 0.4);
		border-radius: 6px;
		cursor: pointer;
		letter-spacing: 0.08em;
		white-space: nowrap;
		transition: all 0.2s ease;
	}
	button:hover:not(:disabled) {
		background: var(--accent);
		color: var(--bg);
		border-color: var(--accent);
	}
	button:disabled {
		opacity: 0.3;
		cursor: not-allowed;
	}

	.divider {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		margin: 0.8rem 0;
		font-size: 0.7rem;
		color: var(--text-ghost);
	}
	.divider::before, .divider::after {
		content: '';
		flex: 1;
		height: 1px;
		background: rgba(255,255,255,0.05);
	}

	.geo-btn {
		width: 100%;
		font-family: var(--serif);
		font-size: 0.9rem;
		font-style: italic;
		padding: 0.7rem;
	}

	.state-pick {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.8rem;
	}
	select {
		flex: 1;
		font-family: var(--serif);
		font-size: 0.9rem;
		padding: 0.6rem 0.8rem;
		background: rgba(0,0,0,0.4);
		color: var(--text);
		border: 1px solid rgba(255,255,255,0.06);
		border-radius: 6px;
		appearance: none;
		outline: none;
	}

	.err {
		color: var(--accent);
		font-size: 0.85rem;
		font-style: italic;
		margin-top: 1rem;
		max-width: 460px;
	}

	.loading {
		color: var(--text-dim);
		font-size: 0.85rem;
		font-style: italic;
		margin-top: 1rem;
	}

	.hint {
		font-size: 0.7rem;
		color: var(--text-ghost);
		margin-top: 2rem;
		max-width: 400px;
		line-height: 1.5;
	}

	.credit {
		position: absolute;
		bottom: 1.2rem;
		right: var(--section-pad);
		font-family: var(--mono);
		font-size: 0.55rem;
		color: var(--text-ghost);
		opacity: 0.5;
		text-decoration: none;
		max-width: 260px;
		text-align: right;
		line-height: 1.4;
		letter-spacing: 0.02em;
		transition: opacity 0.3s;
	}
	.credit:hover { opacity: 1; }

	@media (max-width: 768px) {
		.hero { padding: 1.5rem; }
		.input-group { max-width: 100%; }
	}
</style>
