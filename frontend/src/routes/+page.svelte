<script>
	import { onMount } from 'svelte';
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

	async function onTrace(subregionId) {
		loading = true;
		error = null;
		console.log('[unearthed] tracing subregion:', subregionId);
		try {
			mineData = await fetchMineForMe(subregionId);
			mineData.subregion_id = subregionId;
			console.log('[unearthed] loaded:', mineData.mine, '→', mineData.plant);
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
	<title>Unearthed{mineData ? ` — ${mineData.mine}, ${mineData.mine_state}` : ''}</title>
	<meta name="description" content="Find the coal mine under contract to your power plant." />
</svelte:head>

{#if !mineData}
	<Hero {loading} {error} onTrace={onTrace} />
{:else}
	<main class="scroll">
		<PlantReveal data={mineData} />
		<MapSection data={mineData} />
		<H3Density />
		<CortexChat subregionId={mineData.subregion_id} mineName={mineData.mine} plantName={mineData.plant} />
		<Ticker data={mineData} />
	</main>
{/if}

<style>
	.scroll { width: 100%; }
</style>
