<script>
	import { onMount, onDestroy } from 'svelte';
	let { data } = $props();

	const SECONDS_IN_YEAR = 365.25 * 24 * 60 * 60;
	const rate = data.tons / SECONDS_IN_YEAR;
	let tons = $state(0);
	let raf = null;
	let t0 = null;

	onMount(() => {
		function tick(now) {
			if (!t0) t0 = now;
			tons = rate * ((now - t0) / 1000);
			raf = requestAnimationFrame(tick);
		}
		raf = requestAnimationFrame(tick);
	});
	onDestroy(() => { if (raf) cancelAnimationFrame(raf); });
</script>

<section class="share">
	<div class="ticker">
		<span class="number">{tons.toFixed(2)}</span>
		<span class="unit">tons extracted while you've been on this page</span>
	</div>

	<div class="lines">
		<p>That coal is leaving <em class="rust">{data.mine_county}</em> right now.</p>
		<p>It is being burned at the <em class="rust">{data.plant}</em> power plant right now.</p>
		<p>Your lights are on right now.</p>
	</div>
</section>

<style>
	.share {
		min-height: 80vh;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--section-pad);
		text-align: center;
	}

	.ticker { margin-bottom: 3.5rem; }

	.number {
		display: block;
		font-family: var(--mono);
		font-size: clamp(3rem, 11vw, 7rem);
		font-weight: 300;
		color: var(--accent);
		line-height: 1;
		letter-spacing: -0.02em;
	}
	.unit {
		display: block;
		font-family: var(--mono);
		font-size: 0.6rem;
		color: var(--text-ghost);
		letter-spacing: 0.15em;
		text-transform: uppercase;
		margin-top: 0.6rem;
	}

	.lines p {
		font-family: var(--serif);
		font-size: clamp(1.2rem, 3vw, 1.9rem);
		font-weight: 300;
		color: var(--text-dim);
		margin-bottom: 0.8rem;
		max-width: 520px;
		line-height: 1.4;
	}
	.lines :global(.rust) { color: var(--accent); font-style: italic; }
</style>
