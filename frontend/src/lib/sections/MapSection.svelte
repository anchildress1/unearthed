<script>
	import { onMount, onDestroy } from 'svelte';
	import { reveal } from '$lib/reveal.js';

	let { data } = $props();
	let mapEl;
	let mapError = $state(null);
	let animInterval = null;

	onMount(async () => {
		try {
			if (!window.google?.maps) {
				console.log('[unearthed] loading Google Maps...');
				await loadGoogleMaps();
			}

			const { Map } = await google.maps.importLibrary('maps');

			const mine = { lat: data.mine_coords[0], lng: data.mine_coords[1] };
			const plant = { lat: data.plant_coords[0], lng: data.plant_coords[1] };

			const bounds = new google.maps.LatLngBounds();
			bounds.extend(mine);
			bounds.extend(plant);

			const map = new Map(mapEl, {
				mapTypeId: 'hybrid',
				disableDefaultUI: true,
				zoomControl: true,
				gestureHandling: 'greedy',
				styles: [{ featureType: 'all', elementType: 'labels', stylers: [{ visibility: 'simplified' }] }],
			});
			map.fitBounds(bounds, { top: 100, bottom: 100, left: 100, right: 100 });

			// Build curved arc path
			const arcPath = buildArc(mine, plant, 50);

			// Static arc line
			new google.maps.Polyline({
				map,
				path: arcPath,
				strokeColor: '#c2542d',
				strokeWeight: 2.5,
				strokeOpacity: 0.5,
				geodesic: false,
			});

			// Animated dot traversing the arc
			const dot = new google.maps.Marker({
				map,
				position: arcPath[0],
				icon: {
					path: google.maps.SymbolPath.CIRCLE,
					scale: 5,
					fillColor: '#c2542d',
					fillOpacity: 1,
					strokeColor: '#fff',
					strokeWeight: 1.5,
				},
				zIndex: 10,
			});

			let dotIndex = 0;
			animInterval = setInterval(() => {
				dotIndex = (dotIndex + 1) % arcPath.length;
				dot.setPosition(arcPath[dotIndex]);
			}, 80);

			// Mine marker
			addLabeledMarker(map, mine, 'MINE', data.mine, '#c2542d');
			// Plant marker
			addLabeledMarker(map, plant, 'PLANT', data.plant, '#5a7a5a');

			console.log('[unearthed] map rendered');
		} catch (e) {
			console.error('[unearthed] map error:', e);
			mapError = 'Map could not load.';
		}
	});

	onDestroy(() => { if (animInterval) clearInterval(animInterval); });

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

	function addLabeledMarker(map, pos, type, name, color) {
		const marker = new google.maps.Marker({
			map, position: pos, title: name,
			icon: { path: google.maps.SymbolPath.CIRCLE, scale: 7, fillColor: color, fillOpacity: 1, strokeColor: '#fff', strokeWeight: 2 },
		});
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
		info.open(map, marker);
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
		<span class="legend-item"><span class="line-sample"></span> coal supply route</span>
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

	.line-sample {
		width: 20px;
		height: 2px;
		background: var(--accent);
		opacity: 0.6;
	}
</style>
