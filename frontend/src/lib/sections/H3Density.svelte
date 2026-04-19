<script>
	import { onMount } from 'svelte';
	import { fetchH3Density } from '$lib/api.js';
	import { loadSubregionGeoJSON } from '$lib/geo.js';
	import { reveal } from '$lib/reveal.js';

	let {
		userCoords = null,
		mineCoords = null,
		mineName = '',
		mineState = '',
		subregionId = '',
	} = $props();

	const VIEW_W = 1000;
	const VIEW_H = 520;

	let cells = $state([]);
	let geojson = $state(null);
	let loaded = $state(false);
	let errored = $state(false);
	let hovered = $state(null);

	// Projection bounds — auto-fit to whatever the filtered query returns,
	// padded out so the hexes don't hug the frame edge.
	const bounds = $derived.by(() => {
		let minLat = Infinity, maxLat = -Infinity;
		let minLng = Infinity, maxLng = -Infinity;
		for (const c of cells) {
			const lat = c.LAT ?? c.lat;
			const lng = c.LNG ?? c.lng;
			if (lat == null || lng == null) continue;
			if (lat < minLat) minLat = lat;
			if (lat > maxLat) maxLat = lat;
			if (lng < minLng) minLng = lng;
			if (lng > maxLng) maxLng = lng;
		}
		for (const p of [userCoords, mineCoords]) {
			if (!p) continue;
			const [lat, lng] = p;
			if (lat < minLat) minLat = lat;
			if (lat > maxLat) maxLat = lat;
			if (lng < minLng) minLng = lng;
			if (lng > maxLng) maxLng = lng;
		}
		// Sensible continental US fallback if no cells returned yet.
		if (!Number.isFinite(minLat)) {
			return { minLat: 24, maxLat: 49.5, minLng: -125, maxLng: -66 };
		}
		const padLat = Math.max(0.4, (maxLat - minLat) * 0.12);
		const padLng = Math.max(0.4, (maxLng - minLng) * 0.12);
		return {
			minLat: minLat - padLat,
			maxLat: maxLat + padLat,
			minLng: minLng - padLng,
			maxLng: maxLng + padLng,
		};
	});

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

	const userProj = $derived(
		userCoords ? project(userCoords[0], userCoords[1]) : null,
	);
	const mineProj = $derived(
		mineCoords ? project(mineCoords[0], mineCoords[1]) : null,
	);

	const subregionPaths = $derived.by(() => {
		if (!geojson) return [];
		return buildSubregionPaths(geojson);
	});

	onMount(async () => {
		try {
			const [density, geo] = await Promise.all([
				fetchH3Density(5, mineState || null),
				loadSubregionGeoJSON().catch(() => null),
			]);
			cells = density.cells || [];
			if (geo) geojson = geo;
		} catch (e) {
			console.warn('[unearthed] h3-density unavailable:', e.message);
			errored = true;
		} finally {
			loaded = true;
		}
	});

	function project(lat, lon) {
		const { minLat, maxLat, minLng, maxLng } = bounds;
		const x = ((lon - minLng) / (maxLng - minLng)) * VIEW_W;
		const y = VIEW_H - ((lat - minLat) / (maxLat - minLat)) * VIEW_H;
		return [x, y];
	}

	function buildSubregionPaths(geo) {
		// Project each eGRID subregion polygon into the current bounds.
		// Recomputes whenever bounds change (filtered view uses a tighter bbox).
		const out = [];
		for (const feature of geo.features) {
			const sub = feature.properties?.Subregion || '';
			const type = feature.geometry.type;
			const coords = feature.geometry.coordinates;
			const polygons = type === 'MultiPolygon' ? coords : [coords];
			const pathParts = [];
			for (const polygon of polygons) {
				for (const ring of polygon) {
					if (!ring.length) continue;
					const [x0, y0] = project(ring[0][1], ring[0][0]);
					let d = `M${x0.toFixed(1)},${y0.toFixed(1)}`;
					for (let i = 1; i < ring.length; i++) {
						const [x, y] = project(ring[i][1], ring[i][0]);
						d += `L${x.toFixed(1)},${y.toFixed(1)}`;
					}
					d += 'Z';
					pathParts.push(d);
				}
			}
			if (pathParts.length) {
				out.push({ subregion: sub, d: pathParts.join(' ') });
			}
		}
		return out;
	}

	function radius(total) {
		return Math.max(3, Math.min(22, Math.sqrt(total) * 1.6));
	}

	function color(active, total) {
		if (!total) return '#5a7a5a';
		const ratio = active / total;
		const r = Math.round(90 + (194 - 90) * ratio);
		const g = Math.round(122 + (84 - 122) * ratio);
		const b = Math.round(90 + (45 - 90) * ratio);
		return `rgb(${r}, ${g}, ${b})`;
	}

	function onCellHover(c) { hovered = c; }
	function onCellLeave() { hovered = null; }
</script>

<section class="h3" aria-label="Regional coal mining footprint" use:reveal>
	<div class="h3-header">
		<span class="badge">snowflake native · H3 geospatial</span>
		<h3>
			One mine fed your lights.<br/>
			<em>This</em> is {mineState ? `${mineState}'s coal country` : 'the whole seam'}.
		</h3>
		<p class="sub">
			{#if mineState}
				Every coal mine MSHA has on record in {mineState}, clustered into H3 hexes by
				Snowflake's <code>H3_LATLNG_TO_CELL_STRING</code>. Your mine is the anchor —
				hex size scales with mine count, color mixes between
				<span class="rust">rust (still cutting)</span> and
				<span class="moss">moss (abandoned)</span>.
			{:else}
				Every coal mine in MSHA's registry, clustered into H3 hexes by Snowflake's
				<code>H3_LATLNG_TO_CELL_STRING</code>. Size scales with mine count, color mixes
				between <span class="rust">rust (still cutting)</span> and
				<span class="moss">moss (abandoned)</span>.
			{/if}
		</p>
	</div>

	<div class="map-wrap glass">
		{#if !loaded}
			<p class="loading">mapping the footprint…</p>
		{:else if errored || cells.length === 0}
			<p class="loading">Density map temporarily unavailable.</p>
		{:else}
			<svg
				viewBox="0 0 {VIEW_W} {VIEW_H}"
				preserveAspectRatio="xMidYMid meet"
				role="img"
				aria-label="Regional coal mine density"
			>
				<g class="subregion-layer" aria-hidden="true">
					{#each subregionPaths as p}
						<path d={p.d} class:user-region={p.subregion === subregionId} />
					{/each}
				</g>

				<g class="hex-layer">
					{#each cells as c}
						{@const lat = c.LAT ?? c.lat}
						{@const lng = c.LNG ?? c.lng}
						{@const total = c.TOTAL ?? c.total ?? 0}
						{@const active = c.ACTIVE ?? c.active ?? 0}
						{@const abandoned = c.ABANDONED ?? c.abandoned ?? 0}
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
								role="presentation"
								onmouseenter={() => onCellHover({ total, active, abandoned, cx, cy })}
								onmouseleave={onCellLeave}
							/>
						{/if}
					{/each}
				</g>

				{#if mineProj}
					<g class="anchor mine-anchor">
						<circle cx={mineProj[0]} cy={mineProj[1]} r="5" class="anchor-core" />
						<circle cx={mineProj[0]} cy={mineProj[1]} r="11" class="anchor-ring" />
						<text x={mineProj[0] + 14} y={mineProj[1] + 4} class="anchor-label">your mine</text>
					</g>
				{/if}
				{#if userProj}
					<g class="anchor user-anchor">
						<circle cx={userProj[0]} cy={userProj[1]} r="4" class="anchor-core" />
						<circle cx={userProj[0]} cy={userProj[1]} r="9" class="anchor-ring" />
						<text x={userProj[0] + 12} y={userProj[1] + 4} class="anchor-label">you</text>
					</g>
				{/if}

				{#if hovered}
					{@const tx = Math.min(hovered.cx + 14, VIEW_W - 150)}
					{@const ty = Math.max(hovered.cy - 28, 14)}
					<g class="tip" aria-hidden="true">
						<rect x={tx} y={ty} width="140" height="44" rx="3" class="tip-bg" />
						<text x={tx + 8} y={ty + 16} class="tip-text">
							{hovered.total} mines in this hex
						</text>
						<text x={tx + 8} y={ty + 32} class="tip-text tip-sub">
							{hovered.active} active · {hovered.abandoned} closed
						</text>
					</g>
				{/if}
			</svg>
		{/if}
	</div>

	<div class="map-legend">
		<span class="legend-item">
			<svg width="46" height="14" viewBox="0 0 46 14" aria-hidden="true">
				<circle cx="6" cy="7" r="3" fill="#c2542d" fill-opacity="0.5" stroke="#c2542d" />
				<circle cx="22" cy="7" r="5" fill="#c2542d" fill-opacity="0.45" stroke="#c2542d" />
				<circle cx="40" cy="7" r="7" fill="#c2542d" fill-opacity="0.4" stroke="#c2542d" />
			</svg>
			hex size ∝ mine count
		</span>
		<span class="legend-item">
			<span class="swatch rust"></span> still cutting
			<span class="swatch moss"></span> abandoned
		</span>
		{#if subregionId}
			<span class="legend-item">
				<span class="swatch region"></span> your grid subregion ({subregionId})
			</span>
		{/if}
	</div>

	{#if loaded && !errored && totals.mines > 0}
		<div class="tallies">
			<div class="tally">
				<span class="t-value">{totals.mines.toLocaleString()}</span>
				<span class="t-label">
					{mineState ? `coal mines in ${mineState}` : 'coal mines on record'}
				</span>
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

	.subregion-layer path {
		fill: rgba(255, 255, 255, 0.015);
		stroke: rgba(255, 255, 255, 0.12);
		stroke-width: 0.6;
		vector-effect: non-scaling-stroke;
	}
	.subregion-layer path.user-region {
		fill: rgba(194, 84, 45, 0.08);
		stroke: rgba(194, 84, 45, 0.55);
		stroke-width: 1;
	}

	.anchor-core {
		fill: #e8e0d4;
		stroke: #080808;
		stroke-width: 1;
	}
	.mine-anchor .anchor-core {
		fill: var(--accent);
	}
	.anchor-ring {
		fill: none;
		stroke: #e8e0d4;
		stroke-width: 1;
		stroke-opacity: 0.5;
	}
	.mine-anchor .anchor-ring {
		stroke: var(--accent);
		stroke-opacity: 0.75;
	}
	.anchor-label {
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		fill: #e8e0d4;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		paint-order: stroke;
		stroke: #080808;
		stroke-width: 3;
	}
	.mine-anchor .anchor-label {
		fill: var(--accent);
	}

	.tip-bg {
		fill: rgba(8, 8, 8, 0.92);
		stroke: rgba(194, 84, 45, 0.5);
		stroke-width: 0.8;
	}
	.tip-text {
		font-family: 'JetBrains Mono', monospace;
		font-size: 10px;
		fill: #e8e0d4;
		letter-spacing: 0.06em;
	}
	.tip-text.tip-sub {
		fill: #807b75;
		font-size: 9px;
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

	.map-legend {
		display: flex;
		flex-wrap: wrap;
		gap: 1.2rem;
		margin-top: 0.8rem;
		padding: 0 0.2rem;
		font-family: var(--mono);
		font-size: 0.58rem;
		text-transform: uppercase;
		letter-spacing: 0.14em;
		color: var(--text-ghost);
	}
	.map-legend .legend-item {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
	}
	.swatch {
		display: inline-block;
		width: 10px;
		height: 10px;
		border-radius: 50%;
	}
	.swatch.rust { background: var(--accent); }
	.swatch.moss { background: var(--green); }
	.swatch.region {
		background: rgba(194, 84, 45, 0.18);
		border: 1px solid rgba(194, 84, 45, 0.55);
		border-radius: 2px;
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
