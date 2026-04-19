<script>
	import { onMount } from 'svelte';
	import {
		geocodeAddress,
		loadSubregionGeoJSON,
		findSubregion,
		hasCoalData,
		requestLocation,
		subregionForState,
		STATE_TO_SUBREGION,
	} from '$lib/geo.js';
	import { loadGoogleMaps } from '$lib/maps.js';

	let { loading, error, onTrace } = $props();
	let address = $state('');
	let showStatePicker = $state(false);
	let selectedState = $state('');
	let localError = $state(null);

	// Google Places autocomplete — adds a suggestion dropdown beneath the
	// address input without replacing it. If Maps fails to load we silently
	// fall back to the existing submit-and-geocode flow.
	let placesReady = $state(false);
	let predictions = $state([]);
	let showPredictions = $state(false);
	let sessionToken = null;
	let debounceId;

	onMount(async () => {
		try {
			await loadGoogleMaps();
			placesReady = true;
		} catch (e) {
			console.warn('[unearthed] Places suggestions unavailable:', e);
		}
	});

	function newSession() {
		// eslint-disable-next-line no-undef
		sessionToken = new google.maps.places.AutocompleteSessionToken();
	}

	async function fetchPredictions(input) {
		if (!placesReady || !input || input.trim().length < 3) {
			predictions = [];
			return;
		}
		if (!sessionToken) newSession();
		try {
			// eslint-disable-next-line no-undef
			const { suggestions } = await google.maps.places.AutocompleteSuggestion.fetchAutocompleteSuggestions({
				input,
				includedRegionCodes: ['us'],
				sessionToken,
			});
			predictions = (suggestions || [])
				.filter((s) => s.placePrediction)
				.slice(0, 5);
		} catch (e) {
			console.warn('[unearthed] autocomplete fetch failed:', e);
			predictions = [];
		}
	}

	function onAddressInput() {
		showPredictions = true;
		clearTimeout(debounceId);
		debounceId = setTimeout(() => fetchPredictions(address), 180);
	}

	async function selectPrediction(pred) {
		showPredictions = false;
		predictions = [];
		localError = null;
		const displayText = pred.text?.toString?.() ?? pred.text?.text ?? '';
		address = displayText;
		try {
			const place = pred.toPlace();
			await place.fetchFields({ fields: ['location'] });
			// A fetched Place's session token is consumed on the first
			// Details call, so start a fresh one for the next typing session.
			newSession();
			const loc = place.location;
			if (!loc) {
				localError = 'Could not resolve that place. Try another suggestion.';
				return;
			}
			await resolveSubregion(loc.lat(), loc.lng());
		} catch (e) {
			console.error('[unearthed] Place fetch failed:', e);
			localError = 'Could not resolve that place. Try again.';
		}
	}

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
		// If Places gave us at least one prediction, treat submit as
		// "take the top suggestion" — that's what the dropdown is hinting
		// and it avoids a second network hop to a different geocoder.
		if (predictions.length > 0) {
			await selectPrediction(predictions[0].placePrediction);
			return;
		}
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
		// Clear any stale error from an earlier address/geolocation attempt
		// so the user isn't told "CA is outside the US grid" after they've
		// already picked California from the dropdown.
		localError = null;
		const sub = subregionForState(selectedState);
		if (!sub || !hasCoalData(sub)) {
			localError = `No coal data for ${stateLabels[selectedState]}.`;
			return;
		}
		onTrace(sub);
	}
</script>

<section class="hero" aria-label="Find your mine">
	<header class="hero-chrome" aria-hidden="true">
		<span class="rail-num">N° 01</span>
		<span class="rail-rule"></span>
		<span class="rail-label">Locate</span>
	</header>

	<div class="hero-inner">
		<h1>
			<span class="beat">You <span class="rust">came</span> home.</span>
			<span class="beat">You turned <span class="rust">on</span> <em>a light.</em></span>
		</h1>

		<p class="lede">
			Somewhere, a mountain was cut open to keep it burning.<br/>
			<span class="lede-quiet">Tell us where that light is—we'll trace the wire back.</span>
		</p>

		<div class="input-group glass">
			<div class="search-wrap">
				<form class="form" onsubmit={handleSubmit}>
					<input
						id="address"
						name="address"
						type="text"
						placeholder="Address, city, or zip code"
						aria-label="Enter address or zip code"
						bind:value={address}
						oninput={onAddressInput}
						onfocus={() => (showPredictions = true)}
						onblur={() => setTimeout(() => (showPredictions = false), 150)}
						maxlength="200"
						autocomplete="off"
						role="combobox"
						aria-autocomplete="list"
						aria-expanded={showPredictions && predictions.length > 0}
						aria-controls="address-predictions"
						disabled={loading}
					/>
					<button class="primary" type="submit" disabled={loading}>
						{loading ? '…' : 'trace →'}
					</button>
				</form>
				{#if showPredictions && predictions.length > 0}
					<ul id="address-predictions" class="predictions" role="listbox">
						{#each predictions as s}
							{@const pred = s.placePrediction}
							{@const main = pred.mainText?.toString?.() ?? pred.mainText?.text ?? ''}
							{@const secondary = pred.secondaryText?.toString?.() ?? pred.secondaryText?.text ?? ''}
							<li>
								<button
									type="button"
									class="prediction"
									onmousedown={(e) => e.preventDefault()}
									onclick={() => selectPrediction(pred)}
									role="option"
									aria-selected="false"
								>
									<span class="pred-main">{main}</span>
									{#if secondary}<span class="pred-sub">{secondary}</span>{/if}
								</button>
							</li>
						{/each}
					</ul>
				{/if}
			</div>

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
				<p class="hint">Your address is never stored.</p>
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
		display: flex;
		flex-direction: column;
		justify-content: center;
		padding: clamp(2.5rem, 6vh, 4.5rem) clamp(1.5rem, 5vw, 4rem)
			clamp(3rem, 10vh, 5rem);
		position: relative;
	}

	/* Horizontal chrome strip — a quiet editorial marker above the hero
	   copy. Matches SectionRail's top-of-section chrome so every section
	   on the page (Hero through Ticker) reads the same way. */
	.hero-chrome {
		display: flex;
		align-items: center;
		gap: 0.9rem;
		margin-bottom: clamp(1.5rem, 3vh, 2.5rem);
	}
	.rail-num {
		font-family: var(--mono);
		font-size: 0.7rem;
		font-weight: 400;
		letter-spacing: 0.14em;
		color: var(--rust);
		white-space: nowrap;
	}
	.rail-rule {
		height: 1px;
		flex: 0 0 clamp(2.5rem, 6vw, 5rem);
		background: linear-gradient(
			to right,
			rgba(255, 255, 255, 0.18),
			rgba(255, 255, 255, 0.02)
		);
	}
	.rail-label {
		font-family: var(--mono);
		font-size: 0.68rem;
		font-weight: 400;
		letter-spacing: 0.22em;
		text-transform: uppercase;
		color: var(--text-dim);
		white-space: nowrap;
	}

	/* Full-bleed hero content — no two-column grid, no middle-of-page
	   measure cap. Headline runs edge-to-edge with the section's gutter
	   padding as its only constraint. Supporting copy (lede, input group,
	   status) keeps its own narrower measure below so prose stays
	   readable even while the layout feels open. */
	.hero-inner {
		width: 100%;
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		text-align: left;
		gap: 1.5rem;
	}
	.hero-inner > :not(h1) {
		max-width: min(780px, 100%);
		width: 100%;
	}

	/* ---- Headline ----
	   Each sentence is one emotional beat and gets its own single row —
	   no column cap, no mid-sentence wrap. The desktop scale runs up to
	   ~104px and tightens tracking because a display serif at that size
	   otherwise reads airy. Small screens drop `nowrap` so the beat wraps
	   instead of overflowing the viewport. */
	h1 {
		font-family: var(--serif);
		font-size: clamp(2.6rem, 7.8vw, 7rem);
		font-weight: 400;
		line-height: 1.04;
		color: var(--text);
		letter-spacing: -0.025em;
		margin: 0;
		width: 100%;
	}
	h1 .beat {
		display: block;
		white-space: nowrap;
	}
	h1 em {
		font-style: italic;
		color: var(--text);
	}
	:global(.rust) {
		color: var(--rust);
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

	/* Places suggestions dropdown — sits beneath the form, overlays the
	   divider/geolocate block only while active. Matches the glass input
	   aesthetic so it reads as part of the same surface. */
	.search-wrap {
		position: relative;
	}
	.predictions {
		position: absolute;
		top: calc(100% + 0.35rem);
		left: 0;
		right: 0;
		margin: 0;
		padding: 0.3rem;
		list-style: none;
		background: rgba(14, 12, 11, 0.96);
		border: 1px solid rgba(255, 255, 255, 0.08);
		border-radius: 6px;
		box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
		backdrop-filter: blur(8px);
		z-index: 20;
		max-height: 16rem;
		overflow-y: auto;
	}
	.predictions li { margin: 0; padding: 0; }
	.prediction {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		width: 100%;
		padding: 0.55rem 0.75rem;
		background: transparent;
		border: none;
		border-radius: 4px;
		font-family: var(--serif);
		color: var(--text);
		letter-spacing: 0;
		text-transform: none;
		text-align: left;
		cursor: pointer;
		transition: background 0.15s;
	}
	.prediction:hover,
	.prediction:focus-visible {
		background: rgba(255, 255, 255, 0.05);
		color: var(--text);
		border: none;
	}
	.pred-main {
		font-size: 0.95rem;
		line-height: 1.3;
	}
	.pred-sub {
		font-size: 0.78rem;
		color: var(--text-ghost);
		font-style: italic;
		line-height: 1.3;
		margin-top: 0.1rem;
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
		border-color: var(--rust);
		box-shadow: 0 0 0 1px var(--rust-glow);
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
		color: var(--rust);
		border: 1px solid oklch(58% 0.14 36 / 0.4);
		border-radius: 6px;
		cursor: pointer;
		letter-spacing: 0.1em;
		white-space: nowrap;
		transition: all 0.2s ease;
	}
	button:hover:not(:disabled) {
		background: var(--rust);
		color: var(--bg);
		border-color: var(--rust);
	}
	button:disabled {
		opacity: 0.35;
		cursor: not-allowed;
	}
	button.primary {
		background: oklch(58% 0.14 36 / 0.15);
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
		border-color: var(--rust);
	}

	/* ---- Status line (reserved space—never shifts layout) ---- */
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
		color: var(--rust);
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
	/* ---- Photo credit: anchored bottom-right of the hero ---- */
	.credit {
		position: absolute;
		bottom: clamp(1rem, 3vh, 1.8rem);
		right: clamp(1.25rem, 4vw, 3rem);
		font-family: var(--mono);
		font-size: 0.52rem;
		color: var(--text-ghost);
		opacity: 0.45;
		text-decoration: none;
		text-align: right;
		line-height: 1.55;
		letter-spacing: 0.04em;
		transition: opacity 0.3s;
	}
	.credit:hover {
		opacity: 0.9;
	}

	@media (max-width: 720px) {
		.hero {
			padding: 2.25rem 1.25rem 4rem;
		}
		.hero-chrome {
			margin-bottom: 1.25rem;
		}
		.rail-rule {
			flex: 0 0 2rem;
		}
		.hero-inner {
			gap: 1.3rem;
			max-width: 100%;
		}
		/* On narrow screens each beat would overflow the viewport at nowrap —
		   let it wrap onto two lines there so the headline is still readable. */
		h1 .beat {
			white-space: normal;
		}
		.form {
			flex-direction: column;
		}
		button {
			width: 100%;
		}
		.credit {
			position: static;
			text-align: center;
			margin-top: 2rem;
			display: block;
		}
	}

</style>
