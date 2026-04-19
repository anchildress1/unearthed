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
		<p class="eyebrow"><span class="eye-dot"></span> unearthed · a live data memorial</p>

		<h1>
			You <span class="rust">came</span> home.<br/>
			You turned <span class="rust">on</span> <em>a light.</em>
		</h1>

		<p class="lede">
			Somewhere, a mountain was cut open to keep it burning.<br/>
			<span class="lede-quiet">Tell us where that light is — we'll trace the wire back.</span>
		</p>

		<div class="input-group glass">
			<form class="form" onsubmit={handleSubmit}>
				<input
					id="address"
					name="address"
					type="text"
					placeholder="Address, city, or zip code"
					aria-label="Enter address or zip code"
					bind:value={address}
					maxlength="200"
					autocomplete="off"
					disabled={loading}
				/>
				<button class="primary" type="submit" disabled={loading}>
					{loading ? '…' : 'trace →'}
				</button>
			</form>

			<div class="divider"><span>or</span></div>

			<button class="geo-btn" onclick={handleGeolocate} disabled={loading}>
				Use my location
			</button>

			{#if showStatePicker}
				<div class="state-pick">
					<select bind:value={selectedState} aria-label="Select a state">
						<option value="">Select a state…</option>
						{#each states as code}
							<option value={code}>{stateLabels[code] || code}</option>
						{/each}
					</select>
					<button onclick={handleStateGo} disabled={!selectedState || loading}>
						Show me
					</button>
				</div>
			{/if}
		</div>

		<div class="status" aria-live="polite">
			{#if loading}
				<p class="loading">Following the wire back…</p>
			{:else if localError || error}
				<p class="err">{localError || error}</p>
			{:else}
				<p class="hint">
					We never store your address. The wire we follow is public federal data —
					<span class="hint-quiet">MSHA, EIA, EPA, eGRID.</span>
				</p>
			{/if}
		</div>
	</div>

	<a class="credit" href="https://www.flickr.com/photos/nationalmemorialforthemountains/255887679/" target="_blank" rel="noopener">
		Photo: Kent Kessinger · iLoveMountains.org<br/>Flight courtesy SouthWings
	</a>
</section>

<style>
	.hero {
		min-height: 100vh;
		display: grid;
		grid-template-rows: 1fr auto;
		justify-items: center;
		align-items: center;
		padding: clamp(2.5rem, 6vh, 5rem) clamp(1.5rem, 5vw, 4rem);
		position: relative;
	}

	.hero-inner {
		width: 100%;
		max-width: 640px;
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
		gap: 1.6rem;
		/* Lift slightly above optical center so the headline sits in the upper third */
		transform: translateY(-2vh);
	}

	/* ---- Eyebrow ---- */
	.eyebrow {
		display: inline-flex;
		align-items: center;
		gap: 0.55rem;
		font-family: var(--mono);
		font-size: 0.6rem;
		text-transform: uppercase;
		letter-spacing: 0.24em;
		color: var(--text-ghost);
		padding: 0.3rem 0.7rem 0.3rem 0.6rem;
		border: 1px solid rgba(255, 255, 255, 0.06);
		border-radius: 999px;
		background: rgba(255, 255, 255, 0.015);
	}
	.eye-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 8px var(--accent-glow);
		animation: pulse 2.4s ease-in-out infinite;
	}
	@keyframes pulse {
		0%, 100% { opacity: 0.6; }
		50% { opacity: 1; }
	}

	/* ---- Headline ---- */
	h1 {
		font-family: var(--serif);
		font-size: clamp(2.4rem, 6.4vw, 4.6rem);
		font-weight: 400;
		line-height: 1.08;
		color: var(--text);
		letter-spacing: -0.015em;
		margin: 0;
		max-width: 16ch;
	}
	h1 em {
		font-style: italic;
		color: var(--text);
	}
	:global(.rust) {
		color: var(--accent);
	}

	/* ---- Lede ---- */
	.lede {
		font-family: var(--serif);
		font-size: clamp(1rem, 1.4vw, 1.15rem);
		font-weight: 300;
		font-style: italic;
		line-height: 1.65;
		color: var(--text-dim);
		max-width: 44ch;
		margin: 0;
	}
	.lede-quiet {
		color: var(--text-ghost);
		font-style: normal;
		font-size: 0.92em;
	}

	/* ---- Glass input group ---- */
	.input-group {
		width: 100%;
		max-width: 520px;
		padding: 1.25rem 1.25rem 1.4rem;
		display: flex;
		flex-direction: column;
	}

	.form {
		display: flex;
		gap: 0.5rem;
	}

	input[type="text"] {
		flex: 1;
		min-width: 0;
		font-family: var(--serif);
		font-size: 0.98rem;
		padding: 0.85rem 1rem;
		background: rgba(0, 0, 0, 0.42);
		color: var(--text);
		border: 1px solid rgba(255, 255, 255, 0.07);
		border-radius: 6px;
		outline: none;
		transition: border-color 0.2s, box-shadow 0.2s;
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
		font-size: 0.72rem;
		padding: 0.85rem 1.1rem;
		background: transparent;
		color: var(--accent);
		border: 1px solid rgba(194, 84, 45, 0.4);
		border-radius: 6px;
		cursor: pointer;
		letter-spacing: 0.1em;
		white-space: nowrap;
		transition: all 0.2s ease;
	}
	button:hover:not(:disabled) {
		background: var(--accent);
		color: var(--bg);
		border-color: var(--accent);
	}
	button:disabled {
		opacity: 0.35;
		cursor: not-allowed;
	}
	button.primary {
		background: rgba(194, 84, 45, 0.12);
	}

	.divider {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.7rem;
		margin: 1rem 0;
		font-family: var(--mono);
		font-size: 0.6rem;
		text-transform: uppercase;
		letter-spacing: 0.2em;
		color: var(--text-ghost);
	}
	.divider::before,
	.divider::after {
		content: '';
		flex: 1;
		height: 1px;
		background: linear-gradient(
			to right,
			transparent,
			rgba(255, 255, 255, 0.08),
			transparent
		);
	}

	.geo-btn {
		width: 100%;
		font-family: var(--serif);
		font-size: 0.92rem;
		font-style: italic;
		padding: 0.78rem 1rem;
		letter-spacing: 0.02em;
	}

	.state-pick {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.8rem;
	}
	select {
		flex: 1;
		min-width: 0;
		font-family: var(--serif);
		font-size: 0.92rem;
		padding: 0.7rem 0.85rem;
		background: rgba(0, 0, 0, 0.42) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath fill='%239a9490' d='M0 0l5 6 5-6z'/%3E%3C/svg%3E") no-repeat right 0.85rem center;
		color: var(--text);
		border: 1px solid rgba(255, 255, 255, 0.07);
		border-radius: 6px;
		appearance: none;
		outline: none;
		padding-right: 2rem;
	}
	select:focus {
		border-color: var(--accent);
	}

	/* ---- Status line (reserved space — never shifts layout) ---- */
	.status {
		min-height: 3.2rem;
		display: flex;
		align-items: flex-start;
		justify-content: center;
		width: 100%;
		max-width: 520px;
	}
	.err,
	.loading,
	.hint {
		margin: 0;
		line-height: 1.6;
		text-align: center;
	}
	.err {
		color: var(--accent);
		font-size: 0.88rem;
		font-style: italic;
	}
	.loading {
		color: var(--text-dim);
		font-size: 0.88rem;
		font-style: italic;
	}
	.hint {
		font-family: var(--mono);
		font-size: 0.62rem;
		text-transform: uppercase;
		letter-spacing: 0.18em;
		color: var(--text-ghost);
		max-width: 48ch;
	}
	.hint-quiet {
		color: rgba(128, 123, 117, 0.6);
	}

	/* ---- Photo credit ---- */
	.credit {
		justify-self: end;
		align-self: end;
		font-family: var(--mono);
		font-size: 0.52rem;
		color: var(--text-ghost);
		opacity: 0.45;
		text-decoration: none;
		text-align: right;
		line-height: 1.5;
		letter-spacing: 0.04em;
		transition: opacity 0.3s;
	}
	.credit:hover {
		opacity: 0.9;
	}

	@media (max-width: 640px) {
		.hero {
			padding: 2rem 1.25rem 1.25rem;
		}
		.hero-inner {
			gap: 1.3rem;
			transform: none;
		}
		.form {
			flex-direction: column;
		}
		button {
			width: 100%;
		}
		.credit {
			justify-self: center;
			text-align: center;
			margin-top: 2rem;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.eye-dot {
			animation: none;
		}
	}
</style>
