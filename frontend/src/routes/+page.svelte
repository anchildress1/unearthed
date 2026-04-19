<script>
	import { onMount, tick } from 'svelte';
	import { browser } from '$app/environment';
	import Hero from '$lib/sections/Hero.svelte';
	import PlantReveal from '$lib/sections/PlantReveal.svelte';
	import MapSection from '$lib/sections/MapSection.svelte';
	import H3Density from '$lib/sections/H3Density.svelte';
	import CortexChat from '$lib/sections/CortexChat.svelte';
	import Ticker from '$lib/sections/Ticker.svelte';
	import { fetchMineForMe } from '$lib/api.js';

	let mineData = $state(null);
	let loading = $state(false);
	let error = $state(null);
	// Per-trace identity. Incremented on every successful trace so the
	// {#key} block below remounts the reveal tree even when the user
	// retraces within the same eGRID subregion (e.g., a neighbor's
	// address feeds the same grid but has different coordinates).
	// Keying on subregion alone would skip the remount and leave
	// MapSection / H3Density / CortexChat holding stale onMount state.
	let traceNonce = $state(0);
	let resultsEl;

	async function onTrace(subregionId, userCoords = null) {
		loading = true;
		error = null;
		console.log('[unearthed] tracing subregion:', subregionId);
		try {
			mineData = await fetchMineForMe(subregionId);
			mineData.subregion_id = subregionId;
			traceNonce += 1;
			if (userCoords) {
				mineData.user_coords = [userCoords.lat, userCoords.lon];
			}
			console.log('[unearthed] loaded:', mineData.mine, '→', mineData.plant);
			// tick() waits for Svelte to commit the {#if mineData} block so the
			// results container is in the DOM and `resultsEl` is bound before
			// we try to scroll to it.
			if (browser) {
				await tick();
				resultsEl?.scrollIntoView({ behavior: 'smooth', block: 'start' });
			}
		} catch (e) {
			console.error('[unearthed] trace failed:', e);
			error = e.message;
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		if (!browser) return;
		const params = new URLSearchParams(window.location.search);
		const sub = params.get('m');
		if (sub && /^[A-Za-z0-9]{2,10}$/.test(sub)) {
			console.log('[unearthed] share URL:', sub);
			onTrace(sub.toUpperCase());
		}
	});
</script>

<svelte:head>
	<title>Unearthed{mineData ? `—${mineData.mine}, ${mineData.mine_state}` : ''}</title>
	<meta name="description" content="Find the coal mine under contract to your power plant." />
</svelte:head>

<!--
	Hero (N° 01) stays mounted even once a trace returns. Users can always
	search again from the top; a successful trace scrolls the viewport down
	to the results so they read as page 2 rather than replacing page 1.
-->
<Hero {loading} {error} onTrace={onTrace} />
{#if mineData}
	<!--
		{#key} forces every section below to unmount + remount on every
		new trace. Without it, components see new props but keep their
		one-shot onMount state: MapSection's flow overlay stays drawn
		against the previous coordinates, H3Density keeps the old anchor
		markers, CortexChat holds the stale thread. Keyed on `traceNonce`
		rather than `subregion_id` because two addresses in the same
		eGRID subregion share the key — a neighbor's retrace would skip
		the remount. Remounting is cheaper than teaching every section
		to reset itself reactively and matches "the second trace should
		feel like the first trace."
	-->
	{#key traceNonce}
		<main class="scroll" bind:this={resultsEl}>
			<PlantReveal data={mineData} />
			<MapSection data={mineData} />
			<!--
				Two H3Density instances, same data, different viewports. Split
				per user feedback: the grid framing (N° 04) zooms to the eGRID
				subregion polygon so the box containing "your electrons" is
				legible; the seam framing (N° 05) zooms to the hex cluster +
				user/mine anchors so the coal supply shape is visible. The
				first strips the Cortex summary + legend + tallies so the
				chrome only appears once, on the mine framing.
			-->
			<H3Density
				userCoords={mineData.user_coords}
				mineCoords={mineData.mine_coords}
				mineName={mineData.mine}
				mineState={mineData.mine_state}
				subregionId={mineData.subregion_id}
				zoomTo="grid"
				number="04"
				label="Your grid"
				showChrome={false}
			/>
			<H3Density
				userCoords={mineData.user_coords}
				mineCoords={mineData.mine_coords}
				mineName={mineData.mine}
				mineState={mineData.mine_state}
				subregionId={mineData.subregion_id}
				zoomTo="mines"
				number="05"
				label="The seam"
				showChrome={true}
			/>
			<CortexChat subregionId={mineData.subregion_id} mineName={mineData.mine} plantName={mineData.plant} />
			<Ticker data={mineData} />
		</main>
	{/key}
{/if}

<style>
	.scroll { width: 100%; }
</style>
