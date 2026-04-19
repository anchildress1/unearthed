<script>
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
</script>

{#if !mineData}
	<Hero {loading} {error} onTrace={onTrace} />
{:else}
	<div class="scroll-experience">
		<MineReveal data={mineData} />
		<HumanCost data={mineData} />
		<MapSection data={mineData} />
		<YourShare data={mineData} />
		<Chat subregionId={mineData.subregion_id} mineName={mineData.mine} />
	</div>
{/if}

<style>
	.scroll-experience {
		width: 100%;
	}
</style>
