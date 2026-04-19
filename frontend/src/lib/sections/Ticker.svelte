<script>
	import { onMount, onDestroy } from 'svelte';
	const props = $props();

	const SECONDS_IN_YEAR = 365.25 * 24 * 60 * 60;
	let tons = $state(0);
	let raf = null;
	let t0 = null;

	onMount(() => {
		const rate = props.data.tons / SECONDS_IN_YEAR;
		function tick(now) {
			if (!t0) t0 = now;
			tons = rate * ((now - t0) / 1000);
			raf = requestAnimationFrame(tick);
		}
		raf = requestAnimationFrame(tick);
	});
	onDestroy(() => { if (raf) cancelAnimationFrame(raf); });
</script>

<section class="ticker">
	<div class="counter">
		<span class="number">{tons.toFixed(2)}</span>
		<span class="unit">tons extracted while you've been here</span>
	</div>
	<p class="closing">
		That coal left <em>{props.data.mine_county}</em>.
		It burned at <em>{props.data.plant}</em>.
		Your lights stayed on.
	</p>
	<footer class="footer">
		<p>
			Data: <a href="https://www.msha.gov/" target="_blank" rel="noopener">MSHA</a> +
			<a href="https://www.eia.gov/" target="_blank" rel="noopener">EIA</a> (2024, public domain).
			AI: <a href="https://www.snowflake.com/en/data-cloud/cortex/" target="_blank" rel="noopener">Snowflake Cortex Analyst</a>.
		</p>
	</footer>
</section>

<style>
	.ticker {
		min-height: 60vh;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--section-pad);
		text-align: center;
	}

	.counter { margin-bottom: 2.5rem; }

	.number {
		display: block;
		font-family: var(--mono);
		font-size: clamp(3rem, 10vw, 6rem);
		font-weight: 300;
		color: var(--accent);
		line-height: 1;
	}
	.unit {
		display: block;
		font-family: var(--mono);
		font-size: 0.6rem;
		color: var(--text-ghost);
		letter-spacing: 0.15em;
		text-transform: uppercase;
		margin-top: 0.5rem;
	}

	.closing {
		font-family: var(--serif);
		font-size: clamp(1.1rem, 2.5vw, 1.5rem);
		font-weight: 300;
		color: var(--text-dim);
		max-width: 460px;
		line-height: 1.6;
		margin-bottom: 4rem;
	}
	.closing em { color: var(--accent); font-style: italic; }

	.footer {
		padding-top: 2rem;
		border-top: 1px solid rgba(255,255,255,0.04);
	}
	.footer p {
		font-family: var(--mono);
		font-size: 0.55rem;
		color: var(--text-ghost);
		letter-spacing: 0.05em;
	}
	.footer a { color: var(--text-dim); }
	.footer a:hover { color: var(--accent); }
</style>
