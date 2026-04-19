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
		try {
			mineData = await fetchMineForMe(subregionId);
			mineData.subregion_id = subregionId;
		} catch (e) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	// Share URL support: ?m=SRVC
	onMount(() => {
		if (!browser) return;
		const params = new URLSearchParams(window.location.search);
		const sub = params.get('m');
		if (sub && /^[A-Za-z0-9]{2,10}$/.test(sub)) {
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
	<main class="scroll-experience" role="main">
		<MineReveal data={mineData} />
		<HumanCost data={mineData} />
		<MapSection data={mineData} />
		<YourShare data={mineData} />
		<Chat subregionId={mineData.subregion_id} mineName={mineData.mine} />
	</main>
{/if}

<style>
	.scroll-experience {
		width: 100%;
	}
</style>
