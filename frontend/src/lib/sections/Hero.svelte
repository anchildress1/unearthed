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
			localError = 'That location is outside the US grid coverage area. Try the state picker.';
			showStatePicker = true;
			return;
		}
		if (!hasCoalData(subregion)) {
			localError = `Your grid subregion (${subregion}) has no active coal supply chain in our data.`;
			showStatePicker = true;
			return;
		}
		onTrace(subregion);
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
			localError = 'Location access denied. Try entering an address.';
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

<section class="hero">
	<div class="hero__content">
		<div class="hero__label">
			<span class="hero__line"></span>
			<span class="hero__tag">01 &nbsp; THE SWITCH</span>
		</div>
		<h1 class="hero__title">
			You <span class="accent">came</span> home.<br />
			You turned <span class="accent">on</span> <em>a light.</em>
		</h1>

		<p class="hero__sub">tell us where that light is</p>

		<form class="hero__form" onsubmit={handleSubmit}>
			<input
				class="hero__input"
				type="text"
				placeholder="Enter address or zip code"
				bind:value={address}
				maxlength="200"
				autocomplete="off"
				disabled={loading}
			/>
			<button class="hero__btn" type="submit" disabled={loading}>
				{loading ? '...' : 'Trace →'}
			</button>
		</form>

		<div class="hero__or"><span>or</span></div>

		<button class="hero__locate" onclick={handleGeolocate} disabled={loading}>
			Use my location
		</button>

		{#if showStatePicker}
			<div class="hero__state">
				<p class="hero__state-label">Pick your state instead:</p>
				<div class="hero__state-row">
					<select class="hero__select" bind:value={selectedState}>
						<option value="">Select a state...</option>
						{#each states as code}
							<option value={code}>{stateLabels[code] || code}</option>
						{/each}
					</select>
					<button class="hero__btn" onclick={handleStateGo} disabled={!selectedState || loading}>
						Show me
					</button>
				</div>
			</div>
		{/if}

		{#if localError || error}
			<p class="hero__error">{localError || error}</p>
		{/if}

		{#if loading}
			<p class="hero__loading">Tracing your grid...</p>
		{/if}

		<p class="hero__hint">
			We find the nearest coal-burning power plant on your grid — nothing is stored or shared.
		</p>
	</div>

	<a
		class="hero__credit"
		href="https://www.flickr.com/photos/nationalmemorialforthemountains/255887679/"
		target="_blank"
		rel="noopener"
	>Photo: Kent Kessinger / iLoveMountains.org / Flickr — Flight courtesy of SouthWings</a>
</section>

<style>
	.hero {
		min-height: 100vh;
		display: flex;
		align-items: center;
		justify-content: flex-start;
		padding: 2rem 4rem;
		position: relative;
	}

	.hero__content {
		text-align: left;
		max-width: 800px;
		position: relative;
		z-index: 1;
	}

	.hero__label {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-bottom: 1.5rem;
	}

	.hero__line {
		display: block;
		width: 40px;
		height: 1px;
		background: var(--text-muted);
	}

	.hero__tag {
		font-family: var(--font-mono);
		font-size: 0.65rem;
		letter-spacing: 0.2em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.hero__title {
		font-family: var(--font-serif);
		font-size: clamp(2.8rem, 7vw, 5.5rem);
		font-weight: 400;
		line-height: 1.08;
		color: var(--text);
		margin-bottom: 3rem;
	}

	.hero__title :global(.accent) {
		color: var(--accent);
	}

	.hero__title em {
		color: var(--text);
		font-style: italic;
	}

	.hero__sub {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.12em;
		margin-bottom: 1.5rem;
	}

	.hero__form {
		display: flex;
		gap: 0.5rem;
		max-width: 480px;
	}

	.hero__input {
		flex: 1;
		font-family: var(--font-sans);
		font-size: 1rem;
		padding: 0.85rem 1.2rem;
		background: rgba(26, 26, 26, 0.9);
		color: var(--text);
		border: 1px solid var(--border);
		border-radius: 4px;
	}

	.hero__input:focus { outline: none; border-color: var(--accent); }
	.hero__input::placeholder { color: var(--text-muted); }

	.hero__btn {
		font-family: var(--font-mono);
		font-size: 0.85rem;
		padding: 0.85rem 1.5rem;
		background: transparent;
		color: var(--accent);
		border: 1px solid var(--accent);
		border-radius: 4px;
		cursor: pointer;
		letter-spacing: 0.05em;
		white-space: nowrap;
	}

	.hero__btn:hover:not(:disabled) { background: var(--accent); color: var(--bg); }
	.hero__btn:disabled { opacity: 0.4; cursor: not-allowed; }

	.hero__or {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin: 1rem 0;
		color: var(--text-muted);
		font-size: 0.8rem;
		max-width: 480px;
	}

	.hero__or::before, .hero__or::after {
		content: '';
		flex: 1;
		height: 1px;
		background: var(--border);
	}

	.hero__locate {
		font-family: var(--font-sans);
		font-size: 0.95rem;
		padding: 0.75rem 2rem;
		background: transparent;
		color: var(--accent);
		border: 1px solid var(--accent);
		border-radius: 4px;
		cursor: pointer;
	}

	.hero__locate:hover:not(:disabled) { background: var(--accent); color: var(--bg); }

	.hero__state {
		margin: 1.5rem 0;
		max-width: 400px;
	}

	.hero__state-label {
		font-size: 0.85rem;
		color: var(--text-muted);
		margin-bottom: 0.75rem;
	}

	.hero__state-row {
		display: flex;
		gap: 0.5rem;
	}

	.hero__select {
		flex: 1;
		font-family: var(--font-sans);
		font-size: 1rem;
		padding: 0.6rem 1rem;
		background: rgba(26, 26, 26, 0.9);
		color: var(--text);
		border: 1px solid var(--border);
		border-radius: 4px;
		appearance: none;
	}

	.hero__error {
		color: #c45a5a;
		font-size: 0.9rem;
		margin: 1rem 0;
		max-width: 400px;
		padding: 0.75rem;
		background: rgba(196, 90, 90, 0.1);
		border: 1px solid rgba(196, 90, 90, 0.3);
		border-radius: 4px;
	}

	.hero__loading {
		color: var(--text-muted);
		font-size: 0.9rem;
		margin: 1rem 0;
		font-style: italic;
	}

	.hero__hint {
		font-size: 0.75rem;
		color: #4a4540;
		margin-top: 2.5rem;
	}

	.hero__credit {
		position: absolute;
		bottom: 1rem;
		right: 1rem;
		font-size: 0.65rem;
		color: var(--text-muted);
		opacity: 0.4;
		text-decoration: none;
		z-index: 1;
		line-height: 1.3;
		max-width: 280px;
		text-align: right;
	}

	.hero__credit:hover { opacity: 1; color: var(--text); }

	@media (max-width: 768px) {
		.hero { padding: 2rem; }
	}
</style>
