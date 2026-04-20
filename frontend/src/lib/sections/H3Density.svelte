<script>
	import { onMount, onDestroy } from 'svelte';
	import { fetchH3Density } from '$lib/api.js';
	import {
		loadGoogleMaps,
		createDarkMap,
		createLabeledMarker,
		circleIcon,
		MAP_COLORS,
	} from '$lib/maps.js';
	import SectionRail from '$lib/components/SectionRail.svelte';

	// Single hex density map framed tight on the hex cluster — "the shape
	// of extraction." The eGRID subregion is labeled on the user's pin in
	// the upstream route map (N° 03, MapSection) — it never renders as a
	// polygon on either map. This section is only the heatmap.
	let {
		userCoords = null,
		mineCoords = null,
		mineName = '',
		mineId = '',
		mineCounty = '',
		mineState = '',
	} = $props();

	let mapEl;
	let map = null;
	let infoWindow = null;
	let hexMarkers = [];
	// Mine + user pins. Tracked separately from hexMarkers so the cleanup
	// pass doesn't have to reason about which dots are data vs. which are
	// anchors, and so HMR teardown fully detaches them from the map.
	let anchorMarkers = [];
	// Labeled-card overlays (MINE tag) sit on a different overlay pane
	// than Markers, so they get their own teardown list.
	let anchorOverlays = [];

	let cells = $state([]);
	let registryTotals = $state({ mines: 0, active: 0, abandoned: 0 });
	let loaded = $state(false);
	let errored = $state(false);
	let summary = $state('');
	let summaryDegraded = $state(false);
	let cancelled = false;

	const MIN_RADIUS_PX = 4;
	const MAX_RADIUS_PX = 22;

	// Oceanic outliers (MSHA rows with stray coordinates that land the hex in
	// the Atlantic or at null-island) are filtered at the query layer now, so
	// the frontend only drops non-finite coords. Legitimate edges of a
	// coal-producing region—a single mine on a state boundary, for example
	//—stay in frame where an IQR fence used to cut them.
	const filteredCells = $derived.by(() =>
		cells.filter((c) => {
			const lat = Number(c.LAT ?? c.lat);
			const lng = Number(c.LNG ?? c.lng);
			return Number.isFinite(lat) && Number.isFinite(lng);
		}),
	);

	// Tallies must reflect MSHA's full registry, not the hexes visible on the
	// map. The density query drops null-coord rows, ocean outliers, and small
	// clusters (HAVING total >= 5 on the national view) — all fine for
	// rendering, all wrong for a headline number claiming "X mines on
	// record." The API now returns a separate unfiltered totals payload;
	// pass it through verbatim.
	const totals = $derived(registryTotals);

	// Once the geographic outliers are dropped, the remaining totals cluster
	// tightly. A fixed coefficient on sqrt(total) squashes them all against
	// the min clamp—every hex looks the same. Rescale against the filtered
	// range so the dot with the most mines in view always hits the max size
	// and the smallest always hits the min, with sqrt interpolation so a
	// double-count hex doesn't quadruple in area.
	const totalRange = $derived.by(() => {
		let min = Infinity;
		let max = 0;
		for (const c of filteredCells) {
			const t = Number(c.TOTAL ?? c.total) || 0;
			if (t <= 0) continue;
			if (t < min) min = t;
			if (t > max) max = t;
		}
		if (!Number.isFinite(min)) min = 0;
		return { min, max };
	});

	onMount(async () => {
		// Fetch phase: "unavailable" here is the only honest reason to show
		// the user a generic failure message.
		let density;
		try {
			[density] = await Promise.all([
				fetchH3Density(5, mineState || null),
				// Bootstrap first, then pull in just the `maps` library we
				// use here (Map, Marker, InfoWindow, LatLngBounds,
				// SymbolPath). Dynamic import means unused libraries — like
				// `places` or `geometry` — never hit the wire.
				loadGoogleMaps().then(() => google.maps.importLibrary('maps')),
			]);
		} catch (e) {
			// `console.error` (not warn): a data/SDK failure here is a hard
			// outage, not a graceful degradation — no density data at all.
			console.error('[unearthed] h3-density fetch failed:', e);
			errored = true;
			loaded = true;
			return;
		}

		if (cancelled) return;

		cells = density.cells || [];
		const t = density.totals || {};
		registryTotals = {
			mines: Number(t.total) || 0,
			active: Number(t.active) || 0,
			abandoned: Number(t.abandoned) || 0,
		};
		summary = density.summary || '';
		summaryDegraded = Boolean(density.summary_degraded);

		// Render phase: failures here are code bugs, not API outages. We let
		// them surface in the console with a full stack so they're fixable
		// instead of hiding behind "map temporarily unavailable."
		try {
			if (!mapEl) {
				// An unbound container would make `new google.maps.Map(null, …)`
				// silently construct an orphan Map (no throw on some SDK
				// versions). Raise explicitly so the catch below fires.
				throw new Error('map container not bound');
			}
			map = createDarkMap(mapEl);
			infoWindow = new google.maps.InfoWindow({
				disableAutoPan: true,
				headerDisabled: true,
			});
			renderHexes();
			renderAnchors();
			fitToData();
		} catch (e) {
			console.error('[unearthed] h3-density render failed:', e);
			errored = true;
		} finally {
			loaded = true;
		}
	});

	onDestroy(() => {
		cancelled = true;
		for (const m of hexMarkers) m.setMap(null);
		for (const m of anchorMarkers) m.setMap(null);
		for (const o of anchorOverlays) o.setMap(null);
		infoWindow?.close();
		hexMarkers = [];
		anchorMarkers = [];
		anchorOverlays = [];
		infoWindow = null;
		// Null the Map instance itself: Google's Map holds strong refs to
		// its container element and listeners, so HMR and SPA navigation
		// leak without this.
		map = null;
	});

	function renderHexes() {
		if (!map) return;
		for (const c of filteredCells) {
			const lat = Number(c.LAT ?? c.lat);
			const lng = Number(c.LNG ?? c.lng);
			if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
			const total = Number(c.TOTAL ?? c.total) || 0;
			const active = Number(c.ACTIVE ?? c.active) || 0;
			const abandoned = Number(c.ABANDONED ?? c.abandoned) || 0;
			const fill = color(active, total);
			const marker = new google.maps.Marker({
				map,
				position: { lat, lng },
				// Google Maps renders classic Markers with an internal
				// `role="button"`; without a title, axe-core flags each one
				// under `aria-command-name`. The title promotes to an
				// accessible name (and a native tooltip on hover, which is
				// also a UX win — the cluster stops being anonymous dots).
				title: `${total} coal mines in this area · ${active} active, ${abandoned} closed`,
				icon: {
					path: google.maps.SymbolPath.CIRCLE,
					scale: radius(total),
					fillColor: fill,
					fillOpacity: 0.45,
					strokeColor: fill,
					strokeOpacity: 0.9,
					strokeWeight: 0.8,
				},
				zIndex: 5,
				cursor: 'pointer',
			});
			marker.addListener('click', () =>
				openHexInfo({ total, active, abandoned }, marker),
			);
			hexMarkers.push(marker);
		}
	}

	function renderAnchors() {
		if (!map) return;
		// Mine anchor gets a labeled MINE tag so the reader can name their
		// dot in the cluster — the same 3-line card (glyph + MINE + name +
		// MSHA/county) used on the route map, so the two sections read as
		// one voice. The user pin stays label-free: a card over the cluster
		// would block the shape it's trying to show.
		if (mineCoords) {
			const marker = new google.maps.Marker({
				map,
				position: { lat: mineCoords[0], lng: mineCoords[1] },
				title: mineName || 'your mine',
				icon: circleIcon({ color: MAP_COLORS.rust, scale: 6 }),
				zIndex: 20,
			});
			anchorMarkers.push(marker);
			if (mineName) {
				anchorOverlays.push(
					createLabeledMarker(map, marker, {
						type: 'MINE',
						name: mineName,
						subtitle: buildMineSubtitle(),
					}),
				);
			}
		}
		if (userCoords) {
			anchorMarkers.push(new google.maps.Marker({
				map,
				position: { lat: userCoords[0], lng: userCoords[1] },
				title: 'Your location',
				icon: circleIcon({ color: MAP_COLORS.you, scale: 5 }),
				zIndex: 20,
			}));
		}
	}

	// Same format as MapSection's MINE subtitle — identifier · geography —
	// so a reader who scrolls between sections 03 and 04 sees the same line
	// under the same name. Falls back gracefully when optional fields
	// (mine_id, county) are missing in degraded/fallback payloads.
	function buildMineSubtitle() {
		const parts = [];
		if (mineId) parts.push(`MSHA ${mineId}`);
		if (mineCounty && mineState) parts.push(`${mineCounty} Co., ${mineState}`);
		else if (mineState) parts.push(mineState);
		return parts.join(' · ');
	}

	function openHexInfo({ total, active, abandoned }, marker) {
		if (!infoWindow) return;
		const el = document.createElement('div');
		el.style.cssText =
			"font-family:'JetBrains Mono',monospace;font-size:10px;color:#1a1a1a;line-height:1.5;padding:0;min-width:0";
		const a = document.createElement('div');
		a.textContent = `${total.toLocaleString()} mines in this hex`;
		a.style.cssText = 'font-weight:600';
		const b = document.createElement('div');
		b.textContent = `${active.toLocaleString()} active · ${abandoned.toLocaleString()} closed`;
		b.style.cssText = 'color:#5a5550;margin-top:2px';
		el.appendChild(a);
		el.appendChild(b);
		infoWindow.setContent(el);
		infoWindow.open({ map, anchor: marker });
	}

	function fitToData() {
		if (!map) return;
		const bounds = new google.maps.LatLngBounds();
		let any = false;
		// Fit tight on the hex cluster + anchors — "the shape of
		// extraction." No eGRID polygon is drawn here or upstream; the
		// user's subregion is surfaced as text on their pin in MapSection.
		for (const c of filteredCells) {
			const lat = Number(c.LAT ?? c.lat);
			const lng = Number(c.LNG ?? c.lng);
			if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
			bounds.extend({ lat, lng });
			any = true;
		}
		for (const p of [userCoords, mineCoords]) {
			if (!p) continue;
			const lat = Number(p[0]);
			const lng = Number(p[1]);
			if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
			bounds.extend({ lat, lng });
			any = true;
		}
		if (!any) {
			// Continental US fallback so the frame isn't empty.
			bounds.extend({ lat: 24, lng: -125 });
			bounds.extend({ lat: 49.5, lng: -66 });
		}
		map.fitBounds(bounds, { top: 40, bottom: 40, left: 40, right: 40 });
	}

	function radius(total) {
		// Marker SymbolPath.CIRCLE uses `scale` as the circle radius in pixels.
		// Linearly interpolate sqrt(total) across the filtered range so the
		// dot-size variation is always visible no matter how tight the cluster.
		const { min, max } = totalRange;
		if (max <= 0 || total <= 0) return MIN_RADIUS_PX;
		if (max === min) return (MIN_RADIUS_PX + MAX_RADIUS_PX) / 2;
		const sMin = Math.sqrt(min);
		const sMax = Math.sqrt(max);
		const t = (Math.sqrt(total) - sMin) / (sMax - sMin);
		return MIN_RADIUS_PX + t * (MAX_RADIUS_PX - MIN_RADIUS_PX);
	}

	// Abandoned → warm ash (#7a746c). Green reads as "alive/growing," which is
	// the opposite of what an abandoned mine is. Ash reads as "what's left,"
	// which is what these points actually are.
	function color(active, total) {
		if (!total) return '#7a746c';
		const ratio = active / total;
		// Endpoint is --rust in srgb (#be573b). Gradient interpolates in
		// sRGB for simplicity — the perceptual difference vs OKLCH
		// interpolation is negligible across this short hue/chroma jump
		// between ash(#7a746c) and rust(#be573b).
		const r = Math.round(122 + (190 - 122) * ratio);
		const g = Math.round(116 + (87 - 116) * ratio);
		const b = Math.round(108 + (59 - 108) * ratio);
		return `rgb(${r}, ${g}, ${b})`;
	}
</script>

<SectionRail number="04" label="The seam" class="h3-section">
	<div class="section-header" aria-label="Regional coal mining footprint">
		<h2>
			{#if mineState}
				This is <em>{mineState}'s</em> coal country.<br/>
				Your mine is <em>one dot</em> in it.
			{:else}
				This is the country's <em>coal footprint</em>.<br/>
				Your mine is <em>one dot</em> in it.
			{/if}
		</h2>
		<p class="sub">
			{#if mineState}
				Every coal mine MSHA has on record in {mineState}, clustered by
				location. <strong>Bigger dot, more mines in that patch.</strong>
				Color fades from <span class="rust">rust (still cutting)</span> to
				<span class="ash">ash (abandoned and gone)</span>.
			{:else}
				Every coal mine in MSHA's registry, clustered by location.
				<strong>Bigger dot, more mines nearby.</strong> Color fades from
				<span class="rust">rust (still cutting)</span> to
				<span class="ash">ash (abandoned and gone)</span>.
			{/if}
		</p>
		{#if summary}
			<p class="cortex-note" class:degraded={summaryDegraded}>
				<span class="cortex-note-tag">
					{summaryDegraded ? 'On this map' : 'Cortex, on this map'}
				</span>
				{summary}
			</p>
		{/if}
	</div>

	<div class="map-wrap glass">
		{#if !loaded}
			<p class="loading">mapping the footprint…</p>
		{:else if errored}
			<p class="loading">Density map temporarily unavailable.</p>
		{:else if filteredCells.length === 0}
			<!-- API answered successfully but no hexes cleared HAVING/bounds at
			     this resolution. Tallies (from the separate registry totals
			     query) still render below; the map itself just has nothing to
			     plot. Keep the message neutral so it doesn't read as an
			     outage. -->
			<p class="loading">No density cells at this resolution.</p>
		{/if}
		<div
			class="map-container"
			bind:this={mapEl}
			role="img"
			aria-label={mineState
				? `Coal mine density map for ${mineState}`
				: 'Coal mine density map for the US'}
		></div>
	</div>

	<div class="map-legend">
		<span class="legend-item">
			<svg width="56" height="18" viewBox="0 0 56 18" aria-hidden="true">
				<circle cx="5" cy="9" r="3" fill="#be573b" fill-opacity="0.5" stroke="#be573b" />
				<circle cx="22" cy="9" r="5" fill="#be573b" fill-opacity="0.45" stroke="#be573b" />
				<circle cx="45" cy="9" r="8" fill="#be573b" fill-opacity="0.4" stroke="#be573b" />
			</svg>
			hex size ∝ mine count
		</span>
		<span class="legend-item">
			<span class="swatch rust"></span> still cutting
			<span class="swatch ash"></span> abandoned
		</span>
	</div>

	{#if loaded && !errored && totals.mines > 0}
		<div class="tallies">
			<div class="tally">
				<span class="t-value">{totals.mines.toLocaleString()}</span>
				<span class="anchor-primary">
					{mineState ? `coal mines in ${mineState}` : 'coal mines in the US'}
				</span>
				<span class="anchor-secondary">MSHA registry · 1983 to present</span>
			</div>
			<div class="tally">
				<span class="t-value rust">{totals.active.toLocaleString()}</span>
				<span class="anchor-primary">still cutting coal today</span>
				<span class="anchor-secondary">active · the rust dots on the map</span>
			</div>
			<div class="tally">
				<span class="t-value ash">{totals.abandoned.toLocaleString()}</span>
				<span class="anchor-primary">closed, the ground left behind</span>
				<span class="anchor-secondary">abandoned · the ash dots on the map</span>
			</div>
		</div>
	{/if}
</SectionRail>

<style>
	.map-wrap {
		position: relative;
		width: 100%;
		overflow: hidden;
		padding: 0;
	}

	.map-container {
		width: 100%;
		height: clamp(420px, 58vh, 620px);
	}

	.loading {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: var(--mono);
		font-size: 0.7rem;
		color: var(--text-ghost);
		letter-spacing: 0.1em;
		text-transform: uppercase;
		pointer-events: none;
		z-index: 2;
	}

	.map-legend {
		display: flex;
		flex-wrap: wrap;
		gap: 1.2rem;
		margin-top: 0.8rem;
		padding: 0 0.2rem;
		font-family: var(--mono);
		font-size: 0.58rem;
		text-transform: uppercase;
		letter-spacing: 0.14em;
		color: var(--text-ghost);
	}
	.map-legend .legend-item {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
	}
	.swatch {
		display: inline-block;
		width: 10px;
		height: 10px;
		border-radius: 50%;
	}
	.swatch.rust { background: var(--rust); }
	.swatch.ash { background: #a89e92; }

	.tallies {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
		gap: 1rem;
		margin-top: 1.4rem;
		max-width: 780px;
	}
	.tally {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 0.2rem 0.2rem 0.2rem 1rem;
		border-left: 1px solid rgba(255, 255, 255, 0.08);
	}
	.t-value {
		font-family: var(--serif);
		font-size: clamp(1.7rem, 3.5vw, 2.4rem);
		font-weight: 400;
		color: var(--text);
		line-height: 1;
	}
	.t-value.rust { color: var(--rust); }
	.t-value.ash { color: #a89e92; }
</style>
