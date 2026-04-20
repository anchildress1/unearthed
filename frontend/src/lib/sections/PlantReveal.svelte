<script>
	import { onMount } from 'svelte';
	import { fetchEmissions } from '$lib/api.js';
	import SectionRail from '$lib/components/SectionRail.svelte';

	let { data } = $props();
	let emissions = $state(null);
	let emissionsLoaded = $state(false);

	onMount(async () => {
		try {
			const result = await fetchEmissions(data.plant);
			if (result && result.co2_tons != null) {
				emissions = result;
			}
		} catch (e) {
			console.warn('[unearthed] emissions unavailable:', e.message);
		} finally {
			emissionsLoaded = true;
		}
	});

	function formatTons(n) {
		if (n == null) return '—';
		if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
		if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
		return n.toFixed(0);
	}

	function formatAcres(n) {
		if (n == null || !Number.isFinite(n)) return '—';
		if (n >= 10_000) return `${Math.round(n / 1_000).toLocaleString()}K`;
		if (n >= 100) return Math.round(n).toLocaleString();
		return n.toFixed(n >= 10 ? 0 : 1);
	}

	// Short tons of coal recoverable per surface-mined acre, by state. These
	// are conservative midpoints drawn from published regional averages—not
	// mine-specific surveys. The Powder River Basin ships thick, flat seams
	// at hundreds of thousands of tons per acre; Appalachian mines cut thin
	// seams at roughly an order of magnitude less. The fallback covers the
	// interior and western non-PRB states.
	const YIELD_PER_ACRE = {
		WY: 100_000, MT: 100_000, ND: 100_000,
		WV: 15_000, KY: 15_000, VA: 15_000, TN: 15_000,
		PA: 15_000, OH: 15_000, AL: 15_000, MD: 15_000,
	};
	const DEFAULT_YIELD_PER_ACRE = 40_000;

	// 1 acre = 43,560 sq ft; a US football field (including end zones) is
	// 57,564 sq ft. Used to translate acres into a unit a reader can picture.
	const FIELDS_PER_ACRE = 0.757;

	const landDisturbed = $derived.by(() => {
		const tons = Number(data.tons) || 0;
		if (!tons) return null;
		const mineType = (data.mine_type || '').toLowerCase();
		const isSurface =
			mineType.includes('surface') ||
			mineType.includes('strip') ||
			mineType.includes('mountaintop') ||
			mineType.includes('open');
		if (!isSurface) {
			return { isSurface: false, mineType: data.mine_type || 'underground' };
		}
		const yieldPerAcre = YIELD_PER_ACRE[data.mine_state] ?? DEFAULT_YIELD_PER_ACRE;
		const acres = tons / yieldPerAcre;
		return { isSurface: true, acres, fields: acres * FIELDS_PER_ACRE };
	});

	// Cortex Complete occasionally produces prose where the closing paragraph
	// is a near-restatement of an earlier one. Dedup on normalized text so
	// readers never see the same sentence twice back-to-back.
	const paragraphs = $derived.by(() => {
		if (!data.prose) return [];
		const seen = new Set();
		const out = [];
		for (const raw of data.prose.split(/\n{2,}/)) {
			const trimmed = raw.trim();
			if (!trimmed) continue;
			const key = trimmed.toLowerCase().replace(/\s+/g, ' ');
			if (seen.has(key)) continue;
			seen.add(key);
			out.push(trimmed);
		}
		return out;
	});
</script>

<SectionRail number="02" label="Your coal" class="reveal" reveal={{ distance: 18 }}>
	<h3>
		Your <em>kilowatt-hour</em><br/>starts here.
	</h3>

	<div class="prose">
		{#if paragraphs.length > 0}
			{#each paragraphs as paragraph}
				<p>{paragraph}</p>
			{/each}
		{:else}
			<p>
				{data.plant}, operated by {data.plant_operator}, burns coal shipped from
				{data.mine} in {data.mine_county} County, {data.mine_state}.
			</p>
		{/if}
	</div>

	<div class="cards">
		<div class="card glass">
			<span class="card-value rust">{Number(data.tons).toLocaleString()}</span>
			<span class="anchor-primary">tons of coal shipped from this mine</span>
			<span class="anchor-secondary">to {data.plant} · {data.tons_year}</span>
		</div>
		<div class="card glass">
			<span class="card-value">{data.mine_type}</span>
			<span class="anchor-primary">how the seam was cut</span>
			<span class="anchor-secondary">method · MSHA record</span>
		</div>
		<div class="card glass">
			<span class="card-value region">{data.subregion_id}</span>
			<span class="anchor-primary">your EPA grid subregion</span>
			<span class="anchor-secondary">the boundary your coal pools inside</span>
		</div>
	</div>

	{#if landDisturbed}
		<div class="mountain glass" aria-label="The land this shipment came from">
			<p class="mountain-title">
				<em>The land</em> gave this up. What it gets back depends on what happens next.
			</p>
			{#if landDisturbed.isSurface}
				<div class="mountain-cards">
					<div class="m-card">
						<span class="m-value rust">{formatAcres(landDisturbed.acres)}</span>
						<span class="anchor-primary">acres surface-mined for this one year's shipment</span>
						<span class="anchor-secondary">
							the ground on top of the seam, gone first
						</span>
					</div>
					<div class="m-card">
						<span class="m-value">{formatAcres(landDisturbed.fields)}</span>
						<span class="anchor-primary">football fields of the same ground</span>
						<span class="anchor-secondary">
							the same acres, in a unit you can walk
						</span>
					</div>
				</div>
			{:else}
				<p class="mountain-note">
					A {landDisturbed.mineType.toLowerCase()} mine takes the seam from below,
					not the surface above. The land on top mostly stays. What it leaves behind
					is water, subsidence risk, and bond obligations for whoever inherits the
					ground.
				</p>
			{/if}
			<p class="mountain-source">
				This land can be reclaimed. Whether it is depends on bond dollars, oversight,
				and who keeps paying attention after the last truck leaves.
			</p>
		</div>
	{/if}

	{#if emissions}
		<div class="emissions glass" aria-label="Plant emissions">
			<p class="emissions-title">
				Burning that coal, <em>{data.plant}</em> pushes this into the air every year
			</p>
			<div class="emissions-cards">
				<div class="e-card">
					<span class="e-value rust">{formatTons(emissions.co2_tons)}</span>
					<span class="anchor-primary">tons of heat-trapping gas</span>
					<span class="anchor-secondary">CO<sub>2</sub> · warms the planet</span>
				</div>
				<div class="e-card">
					<span class="e-value">{formatTons(emissions.so2_tons)}</span>
					<span class="anchor-primary">tons of acid-rain pollutant</span>
					<span class="anchor-secondary">SO<sub>2</sub> · kills forests, corrodes stone</span>
				</div>
				<div class="e-card">
					<span class="e-value">{formatTons(emissions.nox_tons)}</span>
					<span class="anchor-primary">tons of smog pollutant</span>
					<span class="anchor-secondary">NO<sub>x</sub> · damages lungs, fuels ozone</span>
				</div>
			</div>
			<p class="emissions-source">
				EPA Clean Air Markets, 2020–present · <strong>Snowflake Marketplace</strong>
			</p>
		</div>
	{/if}
</SectionRail>

<style>
	:global(.section-rail.reveal) {
		min-height: 100vh;
		align-content: center;
	}

	.prose {
		max-width: 600px;
		margin-bottom: 3rem;
	}
	.prose p {
		font-family: var(--serif);
		font-size: clamp(0.95rem, 2vw, 1.15rem);
		font-weight: 300;
		line-height: 1.8;
		color: var(--text-dim);
		margin-bottom: 0.8rem;
	}
	.prose :global(.rust) { color: var(--rust); }

	/* Ledger-look stat grid. The wrapper itself is the hairline: its
	   --rule background bleeds through the 1px gap between children so
	   the cards read as three columns of one document, not three drifting
	   chips. Each child still carries its own glass surface. */
	.cards {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
		gap: 1px;
		max-width: 600px;
		background: var(--rule);
		border: 1px solid var(--border-glass);
		border-radius: 12px;
		overflow: hidden;
	}

	.card {
		padding: 1.2rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		/* Override .glass's own border+radius so the wrapper owns the chrome
		   and only the 1px gap reads as a divider. */
		border: none;
		border-radius: 0;
	}

	.card-value {
		font-family: var(--serif);
		font-size: 1.5rem;
		font-weight: 400;
		color: var(--text);
		line-height: 1;
	}
	.card-value.rust { color: var(--rust); }
	.card-value.region {
		font-family: var(--mono);
		color: var(--text);
		font-size: 1.25rem;
		letter-spacing: 0.05em;
	}

	.mountain {
		margin-top: 1.6rem;
		padding: 1.4rem 1.4rem 1.1rem;
		max-width: 600px;
	}
	.mountain-title {
		font-family: var(--serif);
		font-size: 1rem;
		font-weight: 300;
		color: var(--text-dim);
		margin-bottom: 0.9rem;
		letter-spacing: -0.005em;
	}
	.mountain-title em { font-style: italic; color: var(--rust); }
	.mountain-cards {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 0.6rem;
		margin-bottom: 0.8rem;
	}
	.m-card {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 0.5rem 0.7rem;
		border-left: 1px solid rgba(255, 255, 255, 0.05);
	}
	.m-card:first-child { border-left: none; padding-left: 0; }
	.m-value {
		font-family: var(--mono);
		font-size: 1.3rem;
		font-weight: 300;
		color: var(--text);
		line-height: 1;
	}
	.m-value.rust { color: var(--rust); }
	.mountain-note {
		font-family: var(--serif);
		font-size: 0.9rem;
		font-weight: 300;
		line-height: 1.7;
		color: var(--text-dim);
		margin: 0 0 0.8rem;
	}
	.mountain-source {
		font-family: var(--serif);
		font-size: 0.88rem;
		font-weight: 300;
		line-height: 1.6;
		color: var(--text-dim);
		padding-top: 0.8rem;
		margin: 0;
		border-top: 1px solid rgba(255, 255, 255, 0.04);
	}

	.emissions {
		margin-top: 1.6rem;
		padding: 1.4rem 1.4rem 1.1rem;
		max-width: 600px;
	}
	.emissions-title {
		font-family: var(--serif);
		font-size: 1rem;
		font-weight: 300;
		color: var(--text-dim);
		margin-bottom: 0.9rem;
		letter-spacing: -0.005em;
	}
	.emissions-title em {
		font-style: italic;
		color: var(--rust);
	}
	.emissions-cards {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.6rem;
		margin-bottom: 0.8rem;
	}
	.e-card {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 0.5rem 0.7rem;
		border-left: 1px solid rgba(255, 255, 255, 0.05);
	}
	.e-card:first-child { border-left: none; padding-left: 0; }
	.e-value {
		font-family: var(--mono);
		font-size: 1.3rem;
		font-weight: 300;
		color: var(--text);
		line-height: 1;
	}
	.e-value.rust { color: var(--rust); }
	.emissions-source {
		font-family: var(--mono);
		font-size: 0.55rem;
		text-transform: uppercase;
		letter-spacing: 0.14em;
		color: var(--text-ghost);
		padding-top: 0.6rem;
		border-top: 1px solid rgba(255, 255, 255, 0.04);
	}
	.emissions-source strong {
		color: var(--rust);
		font-weight: 400;
	}

	@media (max-width: 540px) {
		.emissions-cards { grid-template-columns: 1fr 1fr; }
		.e-card:nth-child(3) { border-left: none; padding-left: 0; }
		.mountain-cards { grid-template-columns: 1fr; }
		.m-card { border-left: none; padding-left: 0; }
	}
</style>
