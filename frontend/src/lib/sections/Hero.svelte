<script>
	import { onMount } from 'svelte';
	import {
		loadSubregionGeoJSON,
		findSubregion,
		hasCoalData,
		requestLocation,
	} from '$lib/geo.js';
	import { loadGoogleMaps } from '$lib/maps.js';

	let { loading, error, onTrace } = $props();
	let address = $state('');
	let localError = $state(null);

	// Google Places autocomplete — adds a suggestion dropdown beneath the
	// existing input and resolves every address through GCP. No Nominatim
	// fallback; Places is the single source of geolocation.
	let placesReady = $state(false);
	let predictions = $state([]);
	let showPredictions = $state(false);
	// Counts consecutive autocomplete failures so a transient hiccup doesn't
	// flash a warning under the input, but a sustained outage (quota exceeded,
	// network dead) does surface instead of staying silent. Resets on success.
	let predictionsFailures = $state(0);
	const PREDICTIONS_ERR_THRESHOLD = 2;
	// Modern (2026) pattern: load the Places classes via importLibrary so we
	// never reach into `google.maps.places.*` as a global. Cached after first
	// import.
	let placesLib = null;
	let sessionToken = null;
	let debounceId;
	// Remember the last prediction the user picked from the dropdown so that
	// hitting "trace →" right after a selection skips a redundant
	// autocomplete round-trip and goes straight to Place Details.
	let cachedPrediction = null;

	onMount(async () => {
		try {
			console.log('[unearthed] loading Google Maps…');
			await loadGoogleMaps();
			console.log('[unearthed] Maps bootstrap installed, importing places…');
			placesLib = await google.maps.importLibrary('places');
			console.log('[unearthed] Places library ready:', Object.keys(placesLib));
			placesReady = true;
		} catch (e) {
			console.error('[unearthed] Places library unavailable:', e);
			localError = 'Address search is temporarily unavailable. Try the location button.';
		}
	});

	function newSession() {
		sessionToken = new placesLib.AutocompleteSessionToken();
	}

	async function fetchPredictions(input) {
		if (!placesReady) {
			console.warn('[unearthed] fetchPredictions skipped — places not ready');
			predictions = [];
			return;
		}
		if (!input || input.trim().length < 3) {
			predictions = [];
			return;
		}
		if (!sessionToken) newSession();
		try {
			const { suggestions } = await placesLib.AutocompleteSuggestion.fetchAutocompleteSuggestions({
				input,
				// Hard restrict to US CLDR regions. `region` on its own only
				// biases — it would still happily suggest Paris, France for
				// "par". The app only has coal-supply data for US plants, so
				// non-US suggestions are misleading even as autofill candidates.
				// CLDR codes cover the states + territories we actually carry.
				includedRegionCodes: ['us', 'pr', 'vi', 'gu', 'mp', 'as'],
				language: 'en-US',
				sessionToken,
			});
			const kept = (suggestions || [])
				.filter((s) => s.placePrediction)
				.slice(0, 5);
			console.log(
				'[unearthed] autocomplete:', input,
				'→', (suggestions || []).length, 'suggestions,',
				kept.length, 'predictions kept',
			);
			predictions = kept;
			predictionsFailures = 0;
		} catch (e) {
			console.warn('[unearthed] autocomplete fetch failed:', e);
			predictions = [];
			predictionsFailures += 1;
		}
	}

	function onAddressInput() {
		// User is editing — any cached selection no longer applies.
		cachedPrediction = null;
		showPredictions = true;
		clearTimeout(debounceId);
		debounceId = setTimeout(() => fetchPredictions(address), 180);
	}

	// Picking a suggestion populates the input exactly as if the user had
	// typed the full address. Resolution waits for the trace button — same
	// flow as a hand-typed entry.
	function selectPrediction(pred) {
		const displayText = pred.text?.toString?.() ?? pred.text?.text ?? '';
		address = displayText;
		cachedPrediction = pred;
		predictions = [];
		showPredictions = false;
		localError = null;
	}

	async function resolveFromPrediction(pred) {
		const place = pred.toPlace();
		await place.fetchFields({ fields: ['location'] });
		// Details call consumes the session token — start a fresh one for
		// the next typing session to stay on Autocomplete-Essentials billing.
		newSession();
		const loc = place.location;
		if (!loc) {
			localError = 'Could not resolve that place. Try another address.';
			return;
		}
		await resolveSubregion(loc.lat(), loc.lng());
	}

	async function resolveCurrentAddress() {
		// Prefer the cached prediction if the user picked one and hasn't
		// since edited the input.
		const cachedText = cachedPrediction?.text?.toString?.();
		if (cachedPrediction && cachedText === address) {
			await resolveFromPrediction(cachedPrediction);
			return;
		}
		if (!placesReady) {
			localError = 'Address search is temporarily unavailable. Try the location button.';
			return;
		}
		// No cached pick — ask Places for the top match on whatever the user
		// typed and resolve that. Keeps the single-path GCP contract.
		if (!sessionToken) newSession();
		try {
			const { suggestions } = await placesLib.AutocompleteSuggestion.fetchAutocompleteSuggestions({
				input: address,
				// Same US-territory restriction as fetchPredictions above — when
				// the user hits trace without picking from the dropdown, we ask
				// Places for the top match and resolve that. Without the hard
				// restrict, "london" could resolve to a UK address that has no
				// US eGRID subregion and would error downstream.
				includedRegionCodes: ['us', 'pr', 'vi', 'gu', 'mp', 'as'],
				language: 'en-US',
				sessionToken,
			});
			const top = suggestions?.find((s) => s.placePrediction)?.placePrediction;
			if (!top) {
				localError = 'Could not find that location. Try a full address or zip code.';
				return;
			}
			await resolveFromPrediction(top);
		} catch (e) {
			console.error('[unearthed] resolution failed:', e);
			localError = 'Could not resolve that address. Try again.';
		}
	}

	async function resolveSubregion(lat, lon) {
		const geojson = await loadSubregionGeoJSON();
		const subregion = findSubregion(lat, lon, geojson);
		if (!subregion) {
			// Reached from both geolocate (user is outside the US) and the
			// address flow (user typed a non-US address). The address input
			// above is the same recovery path for either — name it so the
			// outside-US denial path has a visible next step.
			localError =
				'That location is outside the US grid coverage area — try a US address above.';
			return;
		}
		if (!hasCoalData(subregion)) {
			localError = `Your grid subregion (${subregion}) has no active coal supply chain.`;
			return;
		}
		onTrace(subregion, { lat, lon });
	}

	async function handleSubmit(e) {
		e.preventDefault();
		if (!address.trim()) return;
		localError = null;
		await resolveCurrentAddress();
	}

	async function handleGeolocate() {
		localError = null;
		const coords = await requestLocation();
		if (!coords) {
			// Denied / unavailable: the address input is the explicit fallback
			// per AGENTS.md §1 (Places-restricted input covers the geo-denied
			// and outside-US cases). Name it in the copy AND move focus there
			// so the recovery path is physically obvious — otherwise the user
			// sees a dead-end error with the input visually unchanged.
			localError = 'Location access denied — type an address above and hit trace.';
			document.getElementById('address')?.focus();
			return;
		}
		await resolveSubregion(coords.lat, coords.lon);
	}
</script>

<section class="hero" aria-label="Find your mine">
	<div class="hero-layout">
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
		</div>

		<div class="status" aria-live="polite">
			{#if loading}
				<p class="loading">Following the wire back…</p>
			{:else if localError || error}
				<p class="err">{localError || error}</p>
			{:else if predictionsFailures >= PREDICTIONS_ERR_THRESHOLD}
				<p class="err">Address suggestions are temporarily unavailable — type the full address and hit trace.</p>
			{:else}
				<p class="hint">Your address is never stored.</p>
			{/if}
		</div>
		</div>
	</div>

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

	/* Editorial two-column layout. The chrome (N° 01 / rule / LOCATE) is a
	   narrow vertical rail in the left gutter that runs alongside the
	   headline column — like the signature mark in a magazine spread. On
	   narrow screens the rail collapses above the content via the media
	   query below. */
	.hero-layout {
		display: flex;
		align-items: stretch;
		gap: clamp(1.25rem, 3vw, 2.25rem);
		width: 100%;
	}

	/* Vertical chrome rail — pinned in the left gutter and stretched to
	   match the full height of the hero content column. N° caps the top,
	   LOCATE anchors the bottom, and the hairline rule flexes to bridge
	   whatever distance sits between them. The rail "runs the length of
	   the editorial frame." */
	.hero-chrome {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.8rem;
		flex: 0 0 auto;
		padding: 0.35rem 0;
	}
	.rail-num {
		display: block;
		font-family: var(--mono);
		font-size: 0.7rem;
		font-weight: 400;
		letter-spacing: 0.14em;
		color: var(--rust);
		white-space: nowrap;
	}
	/* 1px-wide vertical hairline — `display: block` is required because the
	   element is an empty <span>; without it the width/height don't paint
	   reliably. `margin-left` centers the rule visually under the N°
	   numeral so the column reads as a single stacked marker. */
	.rail-rule {
		display: block;
		width: 1px;
		/* Flex to fill whatever vertical space sits between N° and LOCATE,
		   so the rule spans the full editorial frame height. min-height is
		   a safety floor when the hero content is unusually short. */
		flex: 1 1 auto;
		min-height: 3rem;
		align-self: center;
		background: linear-gradient(
			to bottom,
			rgba(255, 255, 255, 0.04),
			rgba(255, 255, 255, 0.22) 15%,
			rgba(255, 255, 255, 0.22) 85%,
			rgba(255, 255, 255, 0.04)
		);
	}
	.rail-label {
		display: block;
		font-family: var(--mono);
		font-size: 0.68rem;
		font-weight: 400;
		letter-spacing: 0.22em;
		text-transform: uppercase;
		color: var(--text-dim);
		white-space: nowrap;
		/* Rotate so the label reads vertically alongside the headline,
		   classic magazine-rail typography. `writing-mode: vertical-rl`
		   gives real sideways text (not a transform rotation) so it stays
		   accessible to screen readers even though the parent is
		   aria-hidden. */
		writing-mode: vertical-rl;
		transform: rotate(180deg);
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
	/* ---- Narrow-screen hero collapse ---- */
	@media (max-width: 720px) {
		.hero {
			padding: 2.25rem 1.25rem 4rem;
		}
		/* Collapse the two-column editorial layout into a single column
		   on narrow screens — the chrome stacks above the content with
		   the label reading left-to-right again. */
		.hero-layout {
			flex-direction: column;
			gap: 1rem;
		}
		.hero-chrome {
			flex-direction: row;
			align-items: center;
			gap: 0.8rem;
			padding-top: 0;
		}
		.rail-rule {
			width: 2rem;
			height: 1px;
			background: linear-gradient(
				to right,
				rgba(255, 255, 255, 0.22),
				rgba(255, 255, 255, 0.04)
			);
		}
		.rail-label {
			writing-mode: horizontal-tb;
			transform: none;
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
	}

</style>
