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

			// Create the anchor pins immediately so they come in with the
			// flow reveal. Labels wait for pixel-space placement below.
			const anchors = [
				{
					key: 'mine',
					latLng: mine,
					marker: anchorMarker(map, mine, MAP_COLORS.rust, `Coal mine: ${data.mine}`),
					opts: { type: 'MINE', name: data.mine, subtitle: mineSubtitle(data) },
				},
				{
					key: 'plant',
					latLng: plant,
					marker: anchorMarker(map, plant, MAP_COLORS.moss, `Power plant: ${data.plant}`),
					opts: { type: 'PLANT', name: data.plant, subtitle: plantSubtitle(data) },
				},
			];
			if (user) {
				anchors.push({
					key: 'user',
					latLng: user,
					marker: anchorMarker(map, user, MAP_COLORS.you, 'Your meter'),
					opts: { type: 'METER', name: 'your meter', subtitle: meterSubtitle(data) },
				});
			}

			// Wait for fitBounds to settle before placing label cards.
			// Placement has to reason in pixel space — latitude ordering
			// alone stacks cards when mine, plant, and meter all project to
			// nearly the same screen position (common when they share one
			// eGRID subregion). Once idle, pixel Y becomes "what the reader
			// actually sees" and we can scale the card offset with cluster
			// density so cards stay legibly separate even at coincident
			// pins.
			google.maps.event.addListenerOnce(map, 'idle', () => {
				if (cancelled) return;
				attachLabels(map, anchors);
			});
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

	// `title` is required (not optional) so every anchor marker carries an
	// accessible name. Google Maps renders classic Markers with an internal
	// `role="button"`, and axe-core's `aria-command-name` rule fails any
	// anonymous one — so the caller must name the pin for screen readers.
	function anchorMarker(map, pos, color, title) {
		return new google.maps.Marker({
			map,
			position: pos,
			title,
			icon: circleIcon({ color }),
		});
	}

	// Place label cards after the map has fit bounds. Works in pixel space:
	//   - Topmost pin on screen gets the `above` card, bottommost the
	//     `below` card, and any middle pin fans to whichever side it sits
	//     on relative to the pixel-X midpoint of the other two. Pixel Y
	//     (not latitude) decides ordering so a map zoomed into a tight
	//     cluster fans by what the reader actually sees.
	//   - The card offset scales with cluster density. A 14px gap is fine
	//     at 200+ px separation, but below ~140 px the above/below/side
	//     cards start intersecting — scale the offset up so each card
	//     clears its neighbors down to coincident markers.
	function attachLabels(map, anchors) {
		const pts = projectAnchors(map, anchors);
		if (!pts) return;

		const byY = [...pts].sort((a, b) => a.px.y - b.px.y);
		const slot = {};
		slot[byY[0].key] = 'above';
		slot[byY[byY.length - 1].key] = 'below';
		if (byY.length === 3) {
			const middle = byY[1];
			const others = pts.filter((p) => p.key !== middle.key);
			const avgX = others.reduce((s, p) => s + p.px.x, 0) / others.length;
			slot[middle.key] = middle.px.x >= avgX ? 'right' : 'left';
		}

		const offsetPx = clusterOffsetPx(pts);

		for (const p of pts) {
			createLabeledMarker(map, p.marker, {
				...p.opts,
				placement: slot[p.key],
				offsetPx,
			});
		}
	}

	// lat/lng → pixel requires an OverlayView whose draw() has fired at
	// least once (that's when getProjection() returns a real projection).
	// We're already inside the map's `idle` callback so the viewport is
	// final; a bare subclass of OverlayView added + removed in one tick is
	// enough to borrow the projection without leaving DOM behind. Returns
	// null if the projection isn't available (defensive; shouldn't happen
	// post-idle, but skipping labels is better than throwing).
	function projectAnchors(map, anchors) {
		const probe = new google.maps.OverlayView();
		probe.onAdd = () => {};
		probe.draw = () => {};
		probe.onRemove = () => {};
		probe.setMap(map);
		const proj = probe.getProjection();
		if (!proj) {
			probe.setMap(null);
			return null;
		}
		const pts = anchors.map((a) => {
			const px = proj.fromLatLngToDivPixel(
				new google.maps.LatLng(a.latLng.lat, a.latLng.lng),
			);
			return { ...a, px: { x: px.x, y: px.y } };
		});
		probe.setMap(null);
		return pts;
	}

	// Shared offset for every card on this map. Using one value (not
	// per-card) keeps the fan symmetric — otherwise close pairs get
	// mixed gap sizes and the cluster reads lopsided. The tightest
	// pairwise distance sets the scale.
	function clusterOffsetPx(pts) {
		let minDist = Infinity;
		for (let i = 0; i < pts.length; i++) {
			for (let j = i + 1; j < pts.length; j++) {
				const d = Math.hypot(pts[i].px.x - pts[j].px.x, pts[i].px.y - pts[j].px.y);
				if (d < minDist) minDist = d;
			}
		}
		const CLUSTER_PX = 140;
		const BASE_PX = 14;
		const MAX_PX = 80;
		if (!Number.isFinite(minDist) || minDist >= CLUSTER_PX) return BASE_PX;
		return Math.min(MAX_PX, Math.round(BASE_PX + (CLUSTER_PX - minDist) * 0.5));
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
