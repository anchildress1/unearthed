<script>
	import { onMount } from 'svelte';
	import { fetchH3Density } from '$lib/api.js';
	import { reveal } from '$lib/reveal.js';

	// Continental US bounding box — tight enough to keep dots readable.
	const LAT_MIN = 24;
	const LAT_MAX = 49.5;
	const LON_MIN = -125;
	const LON_MAX = -66;
	const VIEW_W = 1000;
	const VIEW_H = 520;

	let cells = $state([]);
	let loaded = $state(false);
	let errored = $state(false);

	const totals = $derived.by(() => {
		let mines = 0;
		let active = 0;
		let abandoned = 0;
		for (const c of cells) {
			mines += c.TOTAL || c.total || 0;
			active += c.ACTIVE || c.active || 0;
			abandoned += c.ABANDONED || c.abandoned || 0;
		}
		return { mines, active, abandoned };
	});

	onMount(async () => {
		try {
			const result = await fetchH3Density(4);
			cells = result.cells || [];
		} catch (e) {
			console.warn('[unearthed] h3-density unavailable:', e.message);
			errored = true;
		} finally {
			loaded = true;
		}
	});

	// Lat/lon → SVG coords (equirectangular projection is fine at this scale).
	function project(lat, lon) {
		const x = ((lon - LON_MIN) / (LON_MAX - LON_MIN)) * VIEW_W;
		const y = VIEW_H - ((lat - LAT_MIN) / (LAT_MAX - LAT_MIN)) * VIEW_H;
		return [x, y];
	}

	function radius(total) {
		// log scale so a single 500-mine hex doesn't drown out the smaller clusters.
		return Math.max(3, Math.min(22, Math.sqrt(total) * 1.6));
	}

	function color(active, total) {
		if (!total) return '#5a7a5a';
		const ratio = active / total; // 0 = all abandoned, 1 = all active
		// Rust (#c2542d) for active, moss-green (#5a7a5a) for abandoned.
		const r = Math.round(90 + (194 - 90) * ratio);
		const g = Math.round(122 + (84 - 122) * ratio);
		const b = Math.round(90 + (45 - 90) * ratio);
		return `rgb(${r}, ${g}, ${b})`;
	}
</script>

<section class="h3" aria-label="National coal mining footprint" use:reveal>
	<div class="h3-header">
		<span class="badge">snowflake native · H3 geospatial</span>
		<h3>
			One mine fed your lights.<br/>
			<em>This</em> is the whole seam.
		</h3>
		<p class="sub">
			Every coal mine in MSHA's registry, clustered into H3 hexes by Snowflake's
			<code>H3_LATLNG_TO_CELL_STRING</code>. <span class="rust">Rust</span> is still cutting.
			<span class="moss">Moss</span> is already gone.
		</p>
	</div>

	<div class="map-wrap glass">
		{#if !loaded}
			<p class="loading">mapping the footprint…</p>
		{:else if errored || cells.length === 0}
			<p class="loading">Density map temporarily unavailable.</p>
		{:else}
			<svg viewBox="0 0 {VIEW_W} {VIEW_H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="US coal mine density">
				{#each cells as c}
					{@const lat = c.LAT ?? c.lat}
					{@const lng = c.LNG ?? c.lng}
					{@const total = c.TOTAL ?? c.total ?? 0}
					{@const active = c.ACTIVE ?? c.active ?? 0}
					{#if lat != null && lng != null}
						{@const [cx, cy] = project(lat, lng)}
						<circle
							{cx}
							{cy}
							r={radius(total)}
							fill={color(active, total)}
							fill-opacity="0.45"
							stroke={color(active, total)}
							stroke-width="0.6"
							stroke-opacity="0.9"
						/>
					{/if}
				{/each}
			</svg>
		{/if}
	</div>

	{#if loaded && !errored && totals.mines > 0}
		<div class="tallies">
			<div class="tally">
				<span class="t-value">{totals.mines.toLocaleString()}</span>
				<span class="t-label">coal mines on record</span>
			</div>
			<div class="tally">
				<span class="t-value rust">{totals.active.toLocaleString()}</span>
				<span class="t-label">still cutting</span>
			</div>
			<div class="tally">
				<span class="t-value moss">{totals.abandoned.toLocaleString()}</span>
				<span class="t-label">abandoned, gone</span>
			</div>
		</div>
	{/if}
</section>

<style>
	.h3 {
		padding: var(--section-pad);
		max-width: 1100px;
		margin: 0 auto;
	}

	.h3-header {
		max-width: 720px;
		margin-bottom: 2rem;
	}

	.badge {
		display: inline-block;
		font-family: var(--mono);
		font-size: 0.55rem;
		text-transform: uppercase;
		letter-spacing: 0.2em;
		color: var(--accent);
		border: 1px solid rgba(194, 84, 45, 0.3);
		padding: 0.25rem 0.6rem;
		border-radius: 3px;
		margin-bottom: 1.3rem;
	}

	h3 {
		font-family: var(--serif);
		font-size: clamp(2rem, 5vw, 3.6rem);
		font-weight: 400;
		line-height: 1.1;
		color: var(--text);
		margin-bottom: 1rem;
		letter-spacing: -0.01em;
	}
	h3 em {
		font-style: italic;
		color: var(--accent);
	}

	.sub {
		font-family: var(--serif);
		font-size: 0.95rem;
		font-weight: 300;
		color: var(--text-dim);
		line-height: 1.7;
	}
	.sub code {
		font-family: var(--mono);
		font-size: 0.8rem;
		color: var(--text);
		background: rgba(255, 255, 255, 0.04);
		padding: 0.05rem 0.4rem;
		border-radius: 3px;
	}
	.sub .rust { color: var(--accent); font-style: italic; }
	.sub .moss { color: var(--green); font-style: italic; }

	.map-wrap {
		padding: 1rem;
		overflow: hidden;
	}
	.map-wrap svg {
		width: 100%;
		height: auto;
		display: block;
	}

	.loading {
		font-family: var(--mono);
		font-size: 0.7rem;
		color: var(--text-ghost);
		text-align: center;
		padding: 3rem 1rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}

	.tallies {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
		gap: 1rem;
		margin-top: 1.4rem;
		max-width: 780px;
	}
	.tally {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		padding: 0.2rem 0.2rem 0.2rem 1rem;
		border-left: 1px solid rgba(255, 255, 255, 0.08);
	}
	.t-value {
		font-family: var(--serif);
		font-size: clamp(1.7rem, 3.5vw, 2.4rem);
		font-weight: 400;
		color: var(--text);
		line-height: 1;
	}
	.t-value.rust { color: var(--accent); }
	.t-value.moss { color: var(--green); }
	.t-label {
		font-family: var(--mono);
		font-size: 0.55rem;
		text-transform: uppercase;
		letter-spacing: 0.15em;
		color: var(--text-ghost);
	}
</style>
