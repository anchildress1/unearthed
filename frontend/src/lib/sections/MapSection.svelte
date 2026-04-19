<script>
	import { onMount, onDestroy } from 'svelte';
	import { reveal } from '$lib/reveal.js';

	let { data } = $props();
	let mapEl;
	let mapError = $state(null);
	let mineDotInterval = null;
	let userDotInterval = null;

	onMount(async () => {
		try {
			if (!window.google?.maps) {
				console.log('[unearthed] loading Google Maps...');
				await loadGoogleMaps();
			}

			const { Map } = await google.maps.importLibrary('maps');
			const { AdvancedMarkerElement } = await google.maps.importLibrary('marker');

			const mine = { lat: data.mine_coords[0], lng: data.mine_coords[1] };
			const plant = { lat: data.plant_coords[0], lng: data.plant_coords[1] };
			const user = data.user_coords
				? { lat: data.user_coords[0], lng: data.user_coords[1] }
				: null;

			const bounds = new google.maps.LatLngBounds();
			bounds.extend(mine);
			bounds.extend(plant);
			if (user) bounds.extend(user);

			const map = new Map(mapEl, {
				mapId: 'UNEARTHED_MAP',
				mapTypeId: 'hybrid',
				disableDefaultUI: true,
				zoomControl: true,
				scrollwheel: false,
				disableDoubleClickZoom: true,
				keyboardShortcuts: false,
			});
			// Tight padding so the chain fills the frame instead of sitting inside a wide margin.
			map.fitBounds(bounds, { top: 40, bottom: 40, left: 40, right: 40 });

			// Arc 1: mine → plant (the supply chain)
			const mineArc = buildArc(mine, plant, 50);
			new google.maps.Polyline({
				map,
				path: mineArc,
				strokeColor: '#c2542d',
				strokeWeight: 2.5,
				strokeOpacity: 0.5,
				geodesic: false,
			});
			const mineDot = new AdvancedMarkerElement({
				map,
				position: mineArc[0],
				content: buildDotElement('#c2542d'),
				zIndex: 10,
			});
			let mineIdx = 0;
			mineDotInterval = setInterval(() => {
				mineIdx = (mineIdx + 1) % mineArc.length;
				mineDot.position = mineArc[mineIdx];
			}, 80);

			// Arc 2: plant → user (the grid delivery)
			if (user) {
				const userArc = buildArc(plant, user, 50);
				new google.maps.Polyline({
					map,
					path: userArc,
					strokeColor: '#5a7a5a',
					strokeWeight: 2,
					strokeOpacity: 0.55,
					geodesic: false,
				});
				const userDot = new AdvancedMarkerElement({
					map,
					position: userArc[0],
					content: buildDotElement('#5a7a5a'),
					zIndex: 10,
				});
				let userIdx = 0;
				userDotInterval = setInterval(() => {
					userIdx = (userIdx + 1) % userArc.length;
					userDot.position = userArc[userIdx];
				}, 80);

				addLabeledMarker(map, AdvancedMarkerElement, user, 'YOU', 'your meter', '#e8e0d4');
			}

			addLabeledMarker(map, AdvancedMarkerElement, mine, 'MINE', data.mine, '#c2542d');
			addLabeledMarker(map, AdvancedMarkerElement, plant, 'PLANT', data.plant, '#5a7a5a');

			console.log('[unearthed] map rendered');
		} catch (e) {
			console.error('[unearthed] map error:', e);
			mapError = 'Map could not load.';
		}
	});

	onDestroy(() => {
		if (mineDotInterval) clearInterval(mineDotInterval);
		if (userDotInterval) clearInterval(userDotInterval);
	});

	function buildArc(from, to, segments) {
		const points = [];
		for (let i = 0; i <= segments; i++) {
			const t = i / segments;
			const lat = from.lat + (to.lat - from.lat) * t;
			const lng = from.lng + (to.lng - from.lng) * t;
			const arc = Math.sin(t * Math.PI) * Math.abs(to.lng - from.lng) * 0.15;
			points.push({ lat: lat + arc, lng });
		}
		return points;
	}

	function buildDotElement(color) {
		const el = document.createElement('div');
		el.style.cssText = `width:10px;height:10px;border-radius:50%;background:${color};border:1.5px solid #fff;box-shadow:0 0 6px ${color}`;
		return el;
	}

	function addLabeledMarker(map, AdvancedMarkerElement, pos, type, name, color) {
		const pin = document.createElement('div');
		pin.style.cssText = `width:14px;height:14px;border-radius:50%;background:${color};border:2px solid #fff;box-shadow:0 0 0 1px rgba(0,0,0,0.3)`;
		const marker = new AdvancedMarkerElement({ map, position: pos, title: name, content: pin });

		const el = document.createElement('div');
		const typeEl = document.createElement('div');
		typeEl.style.cssText = "font-family:'JetBrains Mono',monospace;font-size:10px;color:#807b75;text-transform:uppercase;letter-spacing:0.1em;padding:2px 4px";
		typeEl.textContent = type;
		const nameEl = document.createElement('div');
		nameEl.style.cssText = "font-family:Newsreader,serif;font-size:13px;color:#1a1a1a;padding:0 4px 2px";
		nameEl.textContent = name;
		el.appendChild(typeEl);
		el.appendChild(nameEl);
		const info = new google.maps.InfoWindow({ content: el });
		info.open({ map, anchor: marker });
	}

	function loadGoogleMaps() {
		return new Promise((resolve, reject) => {
			const key = import.meta.env.VITE_GOOGLE_MAPS_KEY || '';
			if (!key) {
				reject(new Error('VITE_GOOGLE_MAPS_KEY not set — map cannot load'));
				return;
			}
			const s = document.createElement('script');
			s.src = `https://maps.googleapis.com/maps/api/js?key=${key}&v=weekly&libraries=maps,marker`;
			s.async = true;
			s.onload = resolve;
			s.onerror = () => reject(new Error('Google Maps failed to load'));
			document.head.appendChild(s);
		});
	}
</script>

<section class="map-section" use:reveal>
	<h3>
		The <em>line</em> — from your meter,<br/>to the stack, to the mountain.
	</h3>

	<div class="map-frame glass">
		{#if mapError}
			<p class="placeholder">{mapError}</p>
		{/if}
		<div class="map-container" bind:this={mapEl}></div>
	</div>

	<div class="legend">
		<span class="legend-item"><span class="dot mine"></span> coal mine</span>
		<span class="legend-item"><span class="dot plant"></span> power plant</span>
		{#if data.user_coords}
			<span class="legend-item"><span class="dot you"></span> you</span>
		{/if}
		<span class="legend-item"><span class="line-sample rust"></span> coal supply</span>
		{#if data.user_coords}
			<span class="legend-item"><span class="line-sample moss"></span> grid delivery</span>
		{/if}
	</div>
</section>

<style>
	.map-section {
		padding: var(--section-pad);
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	h3 {
		font-family: var(--serif);
		font-size: clamp(1.8rem, 4vw, 3rem);
		font-weight: 400;
		color: var(--text);
		text-align: center;
		margin-bottom: 2rem;
		line-height: 1.2;
	}
	h3 em { color: var(--accent); font-style: italic; }

	.map-frame {
		width: 100%;
		max-width: 1000px;
		overflow: hidden;
		padding: 0;
	}

	.map-container {
		width: 100%;
		height: clamp(400px, 55vh, 600px);
		/* Darken Google Maps tiles so the satellite imagery sits in the page
		   palette instead of popping out against the moody dark theme. */
		filter: brightness(0.62) contrast(1.05) saturate(0.8);
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
		gap: 1.5rem;
		margin-top: 1rem;
		font-family: var(--mono);
		font-size: 0.6rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-ghost);
	}

	.legend-item {
		display: flex;
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
	.dot.you { background: #e8e0d4; }

	.line-sample {
		width: 20px;
		height: 2px;
		opacity: 0.6;
	}
	.line-sample.rust { background: var(--accent); }
	.line-sample.moss { background: var(--green); }
</style>
