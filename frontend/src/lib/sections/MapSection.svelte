<script>
	import { onMount, onDestroy } from 'svelte';
	import SectionRail from '$lib/components/SectionRail.svelte';
	import {
		loadGoogleMaps,
		createDarkMap,
		createLabeledMarker,
		circleIcon,
		MAP_COLORS,
	} from '$lib/maps.js';

	let { data } = $props();
	let mapEl;
	let mapError = $state(null);
	let mineDotInterval = null;
	let userDotInterval = null;
	// onMount has an `await` before the first setInterval, so the component
	// can unmount (HMR, fast re-trace) before either interval is assigned.
	// `cancelled` gates every post-await side-effect so we don't strand
	// intervals on a dead component.
	let cancelled = false;

	const ARC_SEGMENTS = 50;
	const DOT_TICK_MS = 80;

	onMount(async () => {
		try {
			await loadGoogleMaps();
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

			// One coal flow—mine → plant → user—drawn as one color so the
			// reader reads it as a single route, not two separate relationships.
			// The stack doesn't interrupt the coal; it only converts it.
			mineDotInterval = animateArc(map, mine, plant, MAP_COLORS.accent, 2.5, 0.55);
			if (user) {
				userDotInterval = animateArc(map, plant, user, MAP_COLORS.accent, 2.5, 0.55);
			}

			// Offset labels from their relative geography so two close-together
			// markers don't stack their InfoWindows on top of each other. Google's
			// InfoWindow anchors at top-center of the marker by default, so we
			// push each label out in the direction that matches where it sits.
			const offsets = computeLabelOffsets({ mine, plant, user });

			createLabeledMarker(
				map,
				anchorMarker(map, mine, MAP_COLORS.accent),
				{ type: 'MINE', name: data.mine, pixelOffset: offsets.mine },
			);
			createLabeledMarker(
				map,
				anchorMarker(map, plant, MAP_COLORS.moss),
				{ type: 'PLANT', name: data.plant, pixelOffset: offsets.plant },
			);
			if (user) {
				createLabeledMarker(
					map,
					anchorMarker(map, user, MAP_COLORS.you),
					{ type: 'YOU', name: 'your meter', pixelOffset: offsets.user },
				);
			}
		} catch (e) {
			console.error('[unearthed] map error:', e);
			mapError = 'Map could not load.';
		}
	});

	onDestroy(() => {
		cancelled = true;
		if (mineDotInterval) clearInterval(mineDotInterval);
		if (userDotInterval) clearInterval(userDotInterval);
	});

	// Sample the same great-circle Google's Polyline (geodesic: true) draws so
	// the animated dot rides the visible line instead of drifting onto a
	// synthetic arc.
	function buildGeodesicArc(from, to) {
		const fromLL = new google.maps.LatLng(from.lat, from.lng);
		const toLL = new google.maps.LatLng(to.lat, to.lng);
		const points = [];
		for (let i = 0; i <= ARC_SEGMENTS; i++) {
			const p = google.maps.geometry.spherical.interpolate(fromLL, toLL, i / ARC_SEGMENTS);
			points.push({ lat: p.lat(), lng: p.lng() });
		}
		return points;
	}

	function animateArc(map, from, to, color, weight, opacity) {
		const arc = buildGeodesicArc(from, to);
		new google.maps.Polyline({
			map,
			path: [from, to],
			strokeColor: color,
			strokeWeight: weight,
			strokeOpacity: opacity,
			geodesic: true,
		});
		const dot = new google.maps.Marker({
			map,
			position: arc[0],
			icon: circleIcon({ color, scale: 5, strokeWeight: 1.5 }),
			zIndex: 10,
			clickable: false,
		});
		let idx = 0;
		return setInterval(() => {
			idx = (idx + 1) % arc.length;
			dot.setPosition(arc[idx]);
		}, DOT_TICK_MS);
	}

	function anchorMarker(map, pos, color) {
		return new google.maps.Marker({
			map,
			position: pos,
			icon: circleIcon({ color }),
		});
	}

	// Fan out the three labels from each other so their InfoWindows don't
	// overlap when the markers are geographically close. We look at the
	// latitude ordering (north-most goes up, south-most goes down) and the
	// east-west spread (close-together points get pushed sideways). The
	// returned offsets are Google Maps `Size` instances, which InfoWindow
	// applies as (dx, dy) pixel offsets from the marker anchor.
	function computeLabelOffsets({ mine, plant, user }) {
		const points = [
			{ key: 'mine', lat: mine.lat, lng: mine.lng },
			{ key: 'plant', lat: plant.lat, lng: plant.lng },
		];
		if (user) points.push({ key: 'user', lat: user.lat, lng: user.lng });

		// Sort by latitude descending (north first) so the northmost label
		// floats above, the southmost drops below, and any middle label side-steps.
		const byLat = [...points].sort((a, b) => b.lat - a.lat);
		const slot = { [byLat[0].key]: 'above', [byLat[byLat.length - 1].key]: 'below' };
		if (byLat.length === 3) slot[byLat[1].key] = 'side';

		// Labels stay anchored to their marker—we only reorient them
		// (above / below / beside) so two close dots don't stack their
		// InfoWindows. Keep the magnitudes small: the dot must still read
		// as the owner of the label.
		const ABOVE = new google.maps.Size(0, -4);
		const BELOW = new google.maps.Size(0, 22);
		const SIDE_LEFT = new google.maps.Size(-22, 8);
		const SIDE_RIGHT = new google.maps.Size(22, 8);

		function sideOffsetFor(key) {
			const me = points.find((p) => p.key === key);
			const others = points.filter((p) => p.key !== key);
			const avgLng = others.reduce((s, p) => s + p.lng, 0) / others.length;
			return me.lng >= avgLng ? SIDE_RIGHT : SIDE_LEFT;
		}

		const out = {};
		for (const p of points) {
			if (slot[p.key] === 'above') out[p.key] = ABOVE;
			else if (slot[p.key] === 'below') out[p.key] = BELOW;
			else out[p.key] = sideOffsetFor(p.key);
		}
		return out;
	}
</script>

<SectionRail number="03" label="The route" class="map-section">
	<div class="map-header">
		<h3>
			Your <em>meter</em> pulls from the stack.<br/>
			The stack pulls from the <em>mountain</em>.
		</h3>
		<p class="sub">
			One rust line is the coal—from the <span class="rust">seam it was cut out of</span>,
			to the <span class="rust">stack that burned it</span>, to
			<span class="rust">your meter</span>. One route, one color.
			<strong>Close markers fan their labels out</strong> so nothing stacks on top of anything else.
		</p>
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
	:global(.section-rail.map-section > .rail-content) {
		max-width: 1100px;
	}

	.map-header {
		max-width: 720px;
		margin-bottom: 2rem;
	}

	.map-frame {
		width: 100%;
		max-width: 1000px;
		overflow: hidden;
		padding: 0;
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
	.dot.mine { background: var(--accent); }
	.dot.plant { background: var(--green); }
	.dot.you { background: #e8dfcc; }

	.line-sample {
		width: 20px;
		height: 2px;
		opacity: 0.6;
	}
	.line-sample.rust { background: var(--accent); }
	.line-sample.moss { background: var(--green); }
</style>
