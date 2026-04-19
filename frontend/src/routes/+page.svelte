<script>
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import Hero from '$lib/sections/Hero.svelte';
	import MineReveal from '$lib/sections/MineReveal.svelte';
	import HumanCost from '$lib/sections/HumanCost.svelte';
	import YourShare from '$lib/sections/YourShare.svelte';
	import MapSection from '$lib/sections/MapSection.svelte';
	import Chat from '$lib/sections/Chat.svelte';
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
			console.log('[unearthed] mine data loaded:', mineData.mine, mineData.mine_state);
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
			console.log('[unearthed] share URL detected:', sub);
			onTrace(sub.toUpperCase());
		}
	});
</script>

<svelte:head>
	<title>unearthed{mineData ? ` — ${mineData.mine}, ${mineData.mine_state}` : ''}</title>
	<meta name="description" content="Find the coal mine under contract to your power plant." />
</svelte:head>

{#if !mineData}
	<Hero {loading} {error} onTrace={onTrace} />
{:else}
	<main class="scroll">
		<MineReveal data={mineData} />
		<MapSection data={mineData} />
		<HumanCost data={mineData} />
		<Chat subregionId={mineData.subregion_id} mineName={mineData.mine} />
		<YourShare data={mineData} />
	</main>
{/if}

<style>
	.scroll {
		width: 100%;
	}
</style>
