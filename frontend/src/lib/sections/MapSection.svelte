<script>
	import { onMount, onDestroy } from 'svelte';
	import SectionRail from '$lib/components/SectionRail.svelte';
	import {
		loadGoogleMaps,
		createDarkMap,
		createFlowOverlay,
		createLabeledMarker,
		circleIcon,
		MAP_COLORS,
	} from '$lib/maps.js';

	let { data } = $props();
	let mapEl;
	let mapError = $state(null);
	let flowOverlay = null;
	// onMount has an `await` before overlay attachment, so the component can
	// unmount (HMR, fast re-trace) before the overlay is assigned. `cancelled`
	// gates every post-await side-effect so we don't strand animation loops
	// on a dead component.
	let cancelled = false;

	onMount(async () => {
		try {
			await loadGoogleMaps();
			// Pull in exactly the libraries this section needs. `maps` gives
			// us `Map`, `Marker`, `LatLngBounds`, `SymbolPath`, `OverlayView`;
			// `geometry` gives `spherical.interpolate` for the flow path.
			// Once imported, the classes are also attached to `google.maps.*`
			// so the existing `new google.maps.Marker(...)` call keeps working.
			await Promise.all([
				google.maps.importLibrary('maps'),
				google.maps.importLibrary('geometry'),
			]);
			if (cancelled) return;

			const mine = { lat: data.mine_coords[0], lng: data.mine_coords[1] };
			const plant = { lat: data.plant_coords[0], lng: data.plant_coords[1] };
			const user = data.user_coords
				? { lat: data.user_coords[0], lng: data.user_coords[1] }
				: null;

			const map = createDarkMap(mapEl);
			const bounds = new google.maps.LatLngBounds();
			bounds.extend(mine);
			bounds.extend(plant);
			if (user) bounds.extend(user);
			map.fitBounds(bounds, { top: 40, bottom: 40, left: 40, right: 40 });

			// One coal flow—mine → plant → user—drawn as one continuous SVG
			// path so the reveal and pulse read as a single route, not two
			// separate relationships. The stack doesn't interrupt the coal;
			// it only converts it.
			const waypoints = user ? [mine, plant, user] : [mine, plant];
			flowOverlay = createFlowOverlay(map, waypoints);

			// Fan the three cards out by relative geography so two close-together
			// markers don't stack their labels. Northmost floats above, southmost
			// drops below, anyone in between slides to the side the other two
			// aren't using. Cards render as HTML overlays (OverlayView), so
			// "above/below/left/right" are real CSS transforms, not nudges.
			const placement = computeLabelPlacement({ mine, plant, user });

			createLabeledMarker(
				map,
				anchorMarker(map, mine, MAP_COLORS.rust),
				{
					type: 'MINE',
					name: data.mine,
					subtitle: mineSubtitle(data),
					placement: placement.mine,
				},
			);
			createLabeledMarker(
				map,
				anchorMarker(map, plant, MAP_COLORS.moss),
				{
					type: 'PLANT',
					name: data.plant,
					subtitle: plantSubtitle(data),
					placement: placement.plant,
				},
			);
			if (user) {
				createLabeledMarker(
					map,
					anchorMarker(map, user, MAP_COLORS.you),
					{
						type: 'METER',
						name: 'your meter',
						subtitle: meterSubtitle(data),
						placement: placement.user,
					},
				);
			}
		} catch (e) {
			console.error('[unearthed] map error:', e);
			mapError = 'Map could not load.';
		}
	});

	onDestroy(() => {
		cancelled = true;
		if (flowOverlay) flowOverlay.setMap(null);
	});

	// Tag subtitles. All three tag kinds share chrome and typography; the
	// subtitle is the place where each kind speaks in its own register
	// (MSHA ID + county, plant operator, EPA subregion). Empty strings
	// render nothing — the helper skips the row — so missing data degrades
	// cleanly instead of showing "undefined". Formats mirror the editorial
	// designs in the PRD: identifier · geography.
	function mineSubtitle(d) {
		const parts = [];
		if (d.mine_id) parts.push(`MSHA ${d.mine_id}`);
		if (d.mine_county && d.mine_state) {
			parts.push(`${d.mine_county} Co., ${d.mine_state}`);
		} else if (d.mine_state) {
			parts.push(d.mine_state);
		}
		return parts.join(' · ');
	}

	function plantSubtitle(d) {
		const parts = [];
		if (d.plant_operator) parts.push(d.plant_operator);
		if (d.subregion_id) parts.push(`subregion ${d.subregion_id}`);
		return parts.join(' · ');
	}

	function meterSubtitle(d) {
		// No reverse-geocoding yet, so the honest identifier is the eGRID
		// subregion the meter pools into. Keeps the tag structure consistent
		// with MINE/PLANT without inventing an address we don't have.
		return d.subregion_id ? `EPA subregion ${d.subregion_id}` : '';
	}

	function anchorMarker(map, pos, color) {
		return new google.maps.Marker({
			map,
			position: pos,
			icon: circleIcon({ color }),
		});
	}

	// Fan the three labels so they don't stack when markers are close.
	// Latitude ordering drives the primary assignment: northmost floats
	// above, southmost drops below. Any middle point slides to whichever
	// side it sits on relative to the other two's longitude midpoint. The
	// returned values are keys of PIN_TRANSFORMS in maps.js.
	function computeLabelPlacement({ mine, plant, user }) {
		const points = [
			{ key: 'mine', lat: mine.lat, lng: mine.lng },
			{ key: 'plant', lat: plant.lat, lng: plant.lng },
		];
		if (user) points.push({ key: 'user', lat: user.lat, lng: user.lng });

		const byLat = [...points].sort((a, b) => b.lat - a.lat);
		const slot = { [byLat[0].key]: 'above', [byLat[byLat.length - 1].key]: 'below' };
		if (byLat.length === 3) slot[byLat[1].key] = 'side';

		function sidePlacementFor(key) {
			const me = points.find((p) => p.key === key);
			const others = points.filter((p) => p.key !== key);
			const avgLng = others.reduce((s, p) => s + p.lng, 0) / others.length;
			return me.lng >= avgLng ? 'right' : 'left';
		}

		const out = {};
		for (const p of points) {
			if (slot[p.key] === 'side') out[p.key] = sidePlacementFor(p.key);
			else out[p.key] = slot[p.key];
		}
		return out;
	}
</script>

<SectionRail number="03" label="The route" class="map-section">
	<div class="section-header">
		<h2>
			Your <em>meter</em> pulls from the stack.<br/>
			The stack pulls from the <em>mountain</em>.
		</h2>
	</div>

	<div class="map-frame glass">
		{#if mapError}
			<p class="placeholder">{mapError}</p>
		{/if}
		<div class="map-container" bind:this={mapEl} role="img" aria-label="Map from coal mine to power plant to your meter"></div>
	</div>

	<div class="legend">
		<span class="legend-item"><span class="dot mine"></span> coal mine</span>
		<span class="legend-item"><span class="dot plant"></span> power plant</span>
		{#if data.user_coords}
			<span class="legend-item"><span class="dot you"></span> you</span>
		{/if}
		<span class="legend-item"><span class="line-sample rust"></span> the coal, from mine to your meter</span>
	</div>
</SectionRail>

<style>
	/* Matted frame. The `.glass` class supplies the 1px border + radius;
	   internal padding insets the map tiles so the frame reads as chrome
	   around the map, not as a flush full-bleed panel. `max-width` keeps
	   the map editorial-width instead of stretching to the full column. */
	.map-frame {
		width: 100%;
		max-width: min(1080px, 100%);
		overflow: hidden;
		padding: clamp(0.6rem, 1.2vw, 1rem);
		/* Left-aligned inside the content column so the matted frame lines
		   up with the headline, sub, legend, and every other section body
		   — all of which flow from the left edge of the rail's content
		   column. Centering made the map a visual outlier. */
		margin: 1rem 0 0;
	}

	.map-container {
		width: 100%;
		height: clamp(420px, 58vh, 620px);
	}

	.placeholder {
		font-family: var(--mono);
		font-size: 0.75rem;
		color: var(--text-ghost);
		text-align: center;
		padding: 2rem;
	}

	.legend {
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

	.legend-item {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
	}

	.dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		border: 1.5px solid #fff;
	}
	.dot.mine { background: var(--rust); }
	.dot.plant { background: var(--green); }
	.dot.you { background: #e8dfcc; }

	.line-sample {
		width: 20px;
		height: 2px;
		opacity: 0.6;
	}
	.line-sample.rust { background: var(--rust); }
</style>
