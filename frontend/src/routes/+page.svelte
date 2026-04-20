<script>
	import { onMount, tick } from 'svelte';
	import { browser } from '$app/environment';
	import { pushState } from '$app/navigation';
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
	let resultsEl = $state();

	async function onTrace(subregionId, userCoords = null, { pushUrl = true } = {}) {
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
			// Push the subregion into the URL on fresh traces so refresh
			// survives: the browser restores the scroll position, onMount
			// replays the trace from ?m=XYZ, and the user lands back on the
			// same results page instead of on empty space below the hero.
			// pushUrl=false when we're *handling* the share URL on mount so
			// we don't stack a duplicate history entry. `pushState` from
			// $app/navigation is SvelteKit's shallow-routing helper — it
			// updates the URL without re-running load functions or
			// desyncing the router's internal history state (bare
			// `window.history.pushState` can cause odd back/forward
			// behavior and full reloads in a SvelteKit app).
			if (browser && pushUrl) {
				const url = new URL(window.location.href);
				url.searchParams.set('m', subregionId);
				pushState(url, {});
			}
			// tick() waits for Svelte to commit the {#if mineData} block so the
			// results container is in the DOM and `resultsEl` is bound before
			// we try to scroll to it. Scroll only on fresh user traces — the
			// share-URL mount replay (pushUrl=false) must leave the viewport
			// alone so the browser's native scroll restoration can return the
			// reader to where they were before refresh. Overriding it would
			// snap them back to `main.scroll` top on every reload.
			if (browser && pushUrl) {
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
			// pushUrl=false: the URL is already ?m=XYZ, don't stack a dup
			// history entry on the initial replay.
			onTrace(sub.toUpperCase(), null, { pushUrl: false });
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
				N° 04 "The seam": a single hex-cluster heatmap framed tight
				on "the shape of extraction." No eGRID polygon here — the
				user's subregion is surfaced only as text on their pin in
				the upstream route map (MapSection, N° 03), so the two
				sections don't compete for the same framing.
			-->
			<H3Density
				userCoords={mineData.user_coords}
				mineCoords={mineData.mine_coords}
				mineName={mineData.mine}
				mineId={mineData.mine_id}
				mineCounty={mineData.mine_county}
				mineState={mineData.mine_state}
			/>
			<CortexChat subregionId={mineData.subregion_id} mineName={mineData.mine} plantName={mineData.plant} />
			<Ticker data={mineData} />
		</main>
	{/key}
{/if}

<style>
	.scroll { width: 100%; }
</style>
