<script>
	import { onMount } from 'svelte';

	let { data } = $props();
	let mapEl;
	let mapError = $state(null);

	onMount(async () => {
		try {
			// Load Google Maps via dynamic script injection
			if (!window.google?.maps) {
				console.log('[unearthed] loading Google Maps API...');
				await loadGoogleMaps();
			}

			const { Map } = await google.maps.importLibrary('maps');
			console.log('[unearthed] Google Maps loaded, creating map');

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
			});
			map.fitBounds(bounds, 80);

			// Mine marker
			new google.maps.Marker({
				map, position: mine,
				title: data.mine,
				icon: {
					path: google.maps.SymbolPath.CIRCLE,
					scale: 9, fillColor: '#c2542d', fillOpacity: 1,
					strokeColor: '#fff', strokeWeight: 2,
				},
			});

			const mineInfo = new google.maps.InfoWindow({
				content: `<div style="font-family:system-ui;font-size:12px;color:#1a1a1a;padding:2px 4px"><strong>Coal Mine</strong><br/>${data.mine}</div>`,
			});
			mineInfo.open(map, new google.maps.Marker({ map, position: mine, visible: false }));

			// Plant marker
			new google.maps.Marker({
				map, position: plant,
				title: data.plant,
				icon: {
					path: google.maps.SymbolPath.CIRCLE,
					scale: 9, fillColor: '#5a7a5a', fillOpacity: 1,
					strokeColor: '#fff', strokeWeight: 2,
				},
			});

			const plantInfo = new google.maps.InfoWindow({
				content: `<div style="font-family:system-ui;font-size:12px;color:#1a1a1a;padding:2px 4px"><strong>Power Plant</strong><br/>${data.plant}</div>`,
			});
			plantInfo.open(map, new google.maps.Marker({ map, position: plant, visible: false }));

			// Flow line mine → plant
			new google.maps.Polyline({
				map,
				path: [mine, plant],
				strokeColor: '#c2542d',
				strokeWeight: 3,
				strokeOpacity: 0.6,
				geodesic: true,
			});

			console.log('[unearthed] map rendered with markers');
		} catch (e) {
			console.error('[unearthed] map failed:', e);
			mapError = 'Map could not load.';
		}
	});

	function loadGoogleMaps() {
		return new Promise((resolve, reject) => {
			// Get the API key from the backend
			fetch('/')
				.then(r => r.text())
				.then(html => {
					const match = html.match(/key:\s*"([^"]+)"/);
					const key = match?.[1] || '';
					const script = document.createElement('script');
					script.src = `https://maps.googleapis.com/maps/api/js?key=${key}&v=weekly&libraries=maps,marker`;
					script.async = true;
					script.onload = resolve;
					script.onerror = () => reject(new Error('Google Maps script failed'));
					document.head.appendChild(script);
				})
				.catch(reject);
		});
	}
</script>

<section class="map-section">
	<div class="map-frame glass">
		{#if mapError}
			<p class="placeholder">{mapError}</p>
		{/if}
		<div class="map-container" bind:this={mapEl}></div>
	</div>
	<p class="chain">
		<span class="mine-label">coal mine</span> {data.mine}
		<span class="arrow">→</span>
		<span class="plant-label">power plant</span> {data.plant}
		<span class="arrow">→</span>
		your grid
	</p>
</section>

<style>
	.map-section {
		padding: var(--section-pad);
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.map-frame {
		width: 100%;
		max-width: 1000px;
		overflow: hidden;
		padding: 0;
	}

	.map-container {
		width: 100%;
		height: clamp(350px, 50vh, 550px);
	}

	.placeholder {
		font-family: var(--mono);
		font-size: 0.75rem;
		color: var(--text-ghost);
		text-align: center;
		padding: 2rem;
	}

	.chain {
		font-family: var(--mono);
		font-size: 0.65rem;
		color: var(--text-ghost);
		letter-spacing: 0.06em;
		margin-top: 1rem;
		text-align: center;
	}

	.mine-label, .plant-label {
		text-transform: uppercase;
		letter-spacing: 0.1em;
		font-size: 0.55rem;
	}

	.mine-label { color: var(--accent); }
	.plant-label { color: var(--green); }
	.arrow { color: var(--accent); margin: 0 0.3rem; }
</style>
