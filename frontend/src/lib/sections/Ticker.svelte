<script>
	import { onMount, onDestroy } from 'svelte';
	import SectionRail from '$lib/components/SectionRail.svelte';
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

<SectionRail number="06" label="While you read" class="ticker-section">
	<div class="counter">
		<span class="number">{tons.toFixed(2)}</span>
		<span class="unit-primary">tons of coal extracted while you've been reading</span>
		<span class="unit-secondary">per-second rate from the {props.data.tons_year} annual shipment</span>
	</div>
	<p class="closing">
		That coal left <em>{props.data.mine_county}</em>.
		It burned at <em>{props.data.plant}</em>.
		Your lights stayed on.
	</p>

	<!--
		Closing dedication. The rest of the page is data; this block is the
		only place the site names the humans behind it. Kept short and flat
		so the thanks doesn't feel performed—two paragraphs, one gratitude
		sentence, one closing fact. The voice follows the same rules as the
		Cortex prose prompt: verbs attach to actors (miners traded, the light
		was paid for), no bridging phrases between the cost and the reader,
		no "still" or "continues" constructions.
	-->
	<aside class="dedication" aria-label="Dedication to the miners">
		<p class="ded-body">
			Behind every ton in that counter is a shift at
			<em>{props.data.mine}</em>. Behind every shift, a miner who gave up
			a morning, a back, a year—and sometimes their life—so the
			switch on your wall would work.
		</p>
		<p class="ded-close">
			To the miners at <em>{props.data.mine}</em>, and to every one
			before them who cut coal so a stranger's city could stay lit:
			<em>thank you</em>. Your bill charges for the watts. It does not
			charge for what they gave.
		</p>
	</aside>

	<footer class="footer">
		<p>
			Data: <a href="https://www.msha.gov/" target="_blank" rel="noopener">MSHA</a> +
			<a href="https://www.eia.gov/" target="_blank" rel="noopener">EIA</a> (2024, public domain).
			AI: <a href="https://www.snowflake.com/en/data-cloud/cortex/" target="_blank" rel="noopener">Snowflake Cortex Analyst</a>.
		</p>
	</footer>
</SectionRail>

<style>
	/* Left-anchored to the rail like the other sections. Keeping it
	   vertically generous so the counter still has room to breathe, but
	   horizontally it flows from column-2's left edge the same as
	   PlantReveal / MapSection / H3 / Cortex. */
	:global(.section-rail.ticker-section > .rail-content) {
		min-height: 60vh;
		max-width: 760px;
	}

	.counter { margin-bottom: 2.5rem; padding-top: 2rem; }

	.number {
		display: block;
		font-family: var(--mono);
		font-size: clamp(3rem, 10vw, 6rem);
		font-weight: 300;
		color: var(--rust);
		line-height: 1;
	}
	/* Three-line anchor pattern—serif plain-English primary, mono
	   uppercase secondary—matches PlantReveal cards + H3 tallies. */
	.unit-primary {
		display: block;
		font-family: var(--serif);
		font-size: 0.95rem;
		font-weight: 400;
		color: var(--text-dim);
		line-height: 1.3;
		margin-top: 0.6rem;
	}
	.unit-secondary {
		display: block;
		font-family: var(--mono);
		font-size: 0.55rem;
		text-transform: uppercase;
		letter-spacing: 0.14em;
		color: var(--text-ghost);
		margin-top: 0.35rem;
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
	.closing em { color: var(--rust); font-style: italic; }

	/* Dedication: quieter than .closing—the page has already said the loud
	   things; this block lowers the voice to acknowledge the people. A thin
	   rule above sets it apart from the closing paragraph without shouting
	   "new section". */
	.dedication {
		max-width: 560px;
		margin: 0 0 3.5rem;
		padding-top: 1.8rem;
		border-top: 1px solid rgba(255, 255, 255, 0.05);
	}
	.ded-body {
		font-family: var(--serif);
		font-size: clamp(1rem, 2vw, 1.2rem);
		font-weight: 300;
		font-style: italic;
		line-height: 1.7;
		color: var(--text-dim);
		margin-bottom: 1rem;
	}
	.ded-close {
		font-family: var(--serif);
		font-size: clamp(1rem, 2vw, 1.2rem);
		font-weight: 400;
		line-height: 1.6;
		color: var(--text);
	}
	.ded-close em {
		color: var(--rust);
		font-style: italic;
	}

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
	.footer a:hover { color: var(--rust); }
</style>
