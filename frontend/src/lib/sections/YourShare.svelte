<script>
	import { onMount, onDestroy } from 'svelte';

	let { data } = $props();

	const SECONDS_IN_YEAR = 365.25 * 24 * 60 * 60;
	const rate = data.tons / SECONDS_IN_YEAR;
	let tonsSoFar = $state(0);
	let rafId = null;
	let startTime = null;

	onMount(() => {
		function tick(now) {
			if (!startTime) startTime = now;
			tonsSoFar = rate * ((now - startTime) / 1000);
			rafId = requestAnimationFrame(tick);
		}
		rafId = requestAnimationFrame(tick);
	});

	onDestroy(() => {
		if (rafId) cancelAnimationFrame(rafId);
	});
</script>

<section class="share">
	<p class="share__pre">04 — YOUR SHARE</p>

	<div class="share__ticker">
		<span class="share__number">{tonsSoFar.toFixed(2)}</span>
		<span class="share__unit">tons extracted since you opened this page</span>
	</div>

	<p class="share__line">
		That coal is leaving <em>{data.mine_county}</em> right now.
	</p>
	<p class="share__line">
		It is being burned at <em>{data.plant}</em> right now.
	</p>
	<p class="share__line">
		Your lights are on right now.
	</p>
</section>

<style>
	.share {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 4rem 2rem;
		text-align: center;
	}

	.share__pre {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.75rem;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		color: #8a8680;
		margin-bottom: 3rem;
	}

	.share__ticker {
		margin-bottom: 4rem;
	}

	.share__number {
		display: block;
		font-family: 'JetBrains Mono', monospace;
		font-size: clamp(3rem, 10vw, 6rem);
		font-weight: 300;
		color: #c4956a;
		line-height: 1;
		margin-bottom: 0.5rem;
	}

	.share__unit {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.75rem;
		color: #8a8680;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}

	.share__line {
		font-family: 'Playfair Display', serif;
		font-size: clamp(1.2rem, 3vw, 1.8rem);
		color: #d4d0c8;
		margin-bottom: 1rem;
		max-width: 500px;
	}

	.share__line em {
		color: #c4956a;
		font-style: italic;
	}
</style>
