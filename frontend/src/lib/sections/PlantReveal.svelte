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

	// MSHA accident record counts, surfaced at the top of section 2 in the
	// unified cost block's people subsection so the human toll anchors the
	// section before the Cortex prose weaves it into narrative. Zero-value
	// rows are omitted individually (an absent line reads cleaner than a
	// zero one), and the whole people subsection is hidden if every field
	// is zero — "no record" is not a story we want to tell twice. The full
	// block hides only when both the people and land subsections are empty.
	const safetyStats = $derived.by(() => {
		const fatalities = Number(data.fatalities) || 0;
		const injuries = Number(data.injuries_lost_time) || 0;
		const daysLost = Number(data.days_lost) || 0;
		const any = fatalities > 0 || injuries > 0 || daysLost > 0;
		return { fatalities, injuries, daysLost, any };
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
	<h2>
		Your <em>kilowatt-hour</em><br/>starts here.
	</h2>

	{#if safetyStats.any || landDisturbed}
		<aside class="cost" aria-labelledby="cost-title">
			<header class="cost-head">
				<p class="cost-eyebrow">
					<span class="glyph" aria-hidden="true">§</span>
					<span>On record</span>
					<span class="eyebrow-sep" aria-hidden="true">·</span>
					<span>MSHA accidents <span class="eyebrow-sep" aria-hidden="true">+</span> regional seam averages</span>
					<span class="eyebrow-sep" aria-hidden="true">·</span>
					<strong>federal public data</strong>
				</p>
				<h3 id="cost-title" class="cost-title">
					What <em>this mine</em> cost.
				</h3>
			</header>

			{#if safetyStats.any}
				<section class="ledger" data-kind="people">
					<p class="ledger-label"><em>The people</em> who worked it.</p>
					<dl class="ledger-rows">
						{#if safetyStats.injuries > 0}
							<div class="row">
								<dt class="numeral">{safetyStats.injuries.toLocaleString()}</dt>
								<dd>
									<span class="row-line">lost-time injuries on record</span>
									<span class="row-sub">shifts that ended at a hospital, not a shower</span>
								</dd>
							</div>
						{/if}
						{#if safetyStats.fatalities > 0}
							<div class="row row--grave">
								<dt class="numeral numeral--grave">{safetyStats.fatalities.toLocaleString()}</dt>
								<dd>
									<span class="row-line"><em>miners killed on the job</em></span>
									<span class="row-sub">fatalities in the MSHA registry</span>
								</dd>
							</div>
						{/if}
						{#if safetyStats.daysLost > 0}
							<div class="row">
								<dt class="numeral">{safetyStats.daysLost.toLocaleString()}</dt>
								<dd>
									<span class="row-line">days of work lost to injury</span>
									<span class="row-sub">time taken from miners and their families</span>
								</dd>
							</div>
						{/if}
					</dl>
				</section>
			{/if}

			{#if safetyStats.any && landDisturbed}
				<div class="cost-break" aria-hidden="true">
					<span class="cost-break-mark">· · ·</span>
				</div>
			{/if}

			{#if landDisturbed}
				<section class="ledger ledger--quiet" data-kind="land">
					<p class="ledger-label"><em>The ground</em> it came from.</p>
					{#if landDisturbed.isSurface}
						<dl class="ledger-inline">
							<div class="inline-row">
								<dt>{formatAcres(landDisturbed.acres)}</dt>
								<dd>acres surface-mined this year</dd>
							</div>
							<span class="inline-sep" aria-hidden="true">/</span>
							<div class="inline-row">
								<dt>{formatAcres(landDisturbed.fields)}</dt>
								<dd>football fields of the same ground</dd>
							</div>
						</dl>
					{:else}
						<p class="land-note">
							A {landDisturbed.mineType.toLowerCase()} mine takes the seam from below,
							not the surface above. The land on top mostly stays. What it leaves behind
							is water, subsidence risk, and bond obligations for whoever inherits the
							ground.
						</p>
					{/if}
				</section>
			{/if}

			<p class="cost-kicker">
				<span class="kicker-land">The acres can be restored.</span>
				<span class="kicker-miners">The miners cannot.</span>
			</p>
		</aside>
	{/if}

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

	/* Unified cost block — the moral center of section 2. Typeset as an
	   editorial cenotaph, not a dashboard card: the block is an inset
	   column with a rust left-gutter (the mine's mark on the page), the
	   people subsection dominates typographically (oversized chiseled
	   numerals, serif italic), and the land subsection collapses to a
	   compact inline beat so the visual weight itself argues the thesis.
	   Closing couplet lands in --rust-bright because this is exactly the
	   charged moment the bright tier exists for. */
	.cost {
		position: relative;
		max-width: min(720px, 100%);
		margin-bottom: 2.2rem;
		padding: 1.8rem 0 1.9rem 1.6rem;
		border-left: 2px solid var(--rust);
		/* A gentle rust wash pooled at the top-left, as if light fell on
		   the stone. No box — the column itself carries the surface. */
		background:
			radial-gradient(180px 120px at 0% 0%, var(--rust-glow), transparent 70%);
	}
	.cost::before {
		content: '';
		position: absolute;
		left: -2px;
		top: 0;
		width: 60px;
		height: 1px;
		background: var(--rust);
		opacity: 0.9;
	}

	.cost-head {
		margin-bottom: 1.6rem;
	}
	.cost-eyebrow {
		display: inline-flex;
		align-items: baseline;
		flex-wrap: wrap;
		gap: 0.45em;
		font-family: var(--mono);
		font-size: 0.58rem;
		text-transform: uppercase;
		letter-spacing: 0.18em;
		color: var(--text-ghost);
		margin: 0 0 0.9rem;
	}
	.cost-eyebrow .glyph {
		color: var(--rust);
		font-family: var(--serif);
		font-style: italic;
		font-size: 0.85rem;
		letter-spacing: 0;
		transform: translateY(0.06em);
	}
	.cost-eyebrow .eyebrow-sep { color: var(--rust); opacity: 0.7; }
	.cost-eyebrow strong { color: var(--text-dim); font-weight: 400; }

	.cost-title {
		font-family: var(--serif);
		font-size: clamp(1.35rem, 2.6vw, 1.7rem);
		font-weight: 300;
		line-height: 1.15;
		letter-spacing: -0.015em;
		color: var(--text);
		margin: 0;
	}
	.cost-title em {
		color: var(--rust);
		font-style: italic;
	}

	/* Ledger — one logical block per subsection. The people ledger takes
	   the full editorial column; the land ledger is marked --quiet and
	   drops to a single inline row so the hierarchy reads visually. */
	.ledger {
		margin-top: 1.3rem;
	}
	.ledger-label {
		font-family: var(--serif);
		font-size: 0.92rem;
		font-weight: 300;
		font-style: normal;
		line-height: 1.5;
		color: var(--text-dim);
		margin: 0 0 1rem;
		letter-spacing: 0.005em;
	}
	.ledger-label em {
		font-style: italic;
		color: var(--text);
	}

	.ledger-rows {
		display: flex;
		flex-direction: column;
		gap: 0;
		margin: 0;
	}
	.row {
		display: grid;
		grid-template-columns: minmax(4.2rem, auto) 1fr;
		align-items: baseline;
		gap: 1.1rem;
		padding: 0.75rem 0;
		border-top: 1px solid rgba(255, 255, 255, 0.05);
	}
	.row:first-child { border-top: none; padding-top: 0; }
	.row:last-child { padding-bottom: 0; }
	.numeral {
		font-family: var(--serif);
		font-weight: 300;
		font-size: clamp(2.2rem, 4.8vw, 3.1rem);
		line-height: 0.95;
		letter-spacing: -0.02em;
		color: var(--text);
		font-variant-numeric: lining-nums tabular-nums;
		text-align: right;
		/* Optical baseline: serif numerals sit slightly above the prose
		   baseline at these sizes — pull them down into alignment. */
		transform: translateY(0.08em);
	}
	.numeral--grave {
		color: var(--rust-bright);
		font-style: italic;
		font-weight: 400;
		font-size: clamp(2.6rem, 5.8vw, 3.8rem);
	}
	.row dd {
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		min-width: 0;
	}
	.row-line {
		font-family: var(--serif);
		font-size: 1rem;
		font-weight: 300;
		line-height: 1.35;
		color: var(--text);
		letter-spacing: 0.002em;
	}
	.row-line em {
		font-style: italic;
		color: var(--rust-bright);
	}
	.row-sub {
		font-family: var(--serif);
		font-size: 0.82rem;
		font-weight: 300;
		font-style: italic;
		line-height: 1.45;
		color: var(--text-ghost);
	}

	/* Typographic break between people and land — three interpuncts in
	   rust, centered on the column. Not a rule; a caesura. */
	.cost-break {
		display: flex;
		justify-content: center;
		margin: 1.4rem 0 0.6rem;
	}
	.cost-break-mark {
		font-family: var(--serif);
		font-size: 1.1rem;
		letter-spacing: 0.4em;
		color: var(--rust);
		opacity: 0.75;
	}

	/* Land ledger — quiet, compact, subordinate. One inline row of data
	   so the hierarchy's argument reads in the typography itself: people
	   get a stone tablet, land gets a margin note. */
	.ledger--quiet .ledger-label { margin-bottom: 0.55rem; }
	.ledger-inline {
		display: flex;
		align-items: baseline;
		flex-wrap: wrap;
		gap: 0.8rem 1.1rem;
		margin: 0;
	}
	.inline-row {
		display: inline-flex;
		align-items: baseline;
		gap: 0.55rem;
	}
	.inline-row dt {
		font-family: var(--serif);
		font-size: 1.4rem;
		font-weight: 300;
		line-height: 1;
		color: var(--text);
		font-variant-numeric: lining-nums tabular-nums;
	}
	.inline-row:first-child dt { color: var(--rust); }
	.inline-row dd {
		margin: 0;
		font-family: var(--serif);
		font-size: 0.88rem;
		font-weight: 300;
		font-style: italic;
		color: var(--text-ghost);
		line-height: 1.4;
	}
	.inline-sep {
		font-family: var(--serif);
		font-size: 1.2rem;
		font-weight: 300;
		color: var(--rust);
		opacity: 0.55;
	}
	.land-note {
		font-family: var(--serif);
		font-size: 0.95rem;
		font-weight: 300;
		line-height: 1.7;
		color: var(--text-dim);
		margin: 0;
		max-width: 56ch;
	}

	/* Closing couplet — the thesis that ties the two halves together.
	   First line is muted, a statement of fact. Second line lands in
	   --rust-bright italic, heavier — the chiseled line. Each sentence
	   gets its own gravity on its own row. */
	.cost-kicker {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		font-family: var(--serif);
		line-height: 1.25;
		margin: 1.9rem 0 0;
		padding-top: 1.3rem;
		border-top: 1px solid rgba(255, 255, 255, 0.05);
	}
	.kicker-land {
		font-size: clamp(1rem, 1.8vw, 1.15rem);
		font-weight: 300;
		font-style: italic;
		color: var(--text-dim);
		letter-spacing: 0.002em;
	}
	.kicker-miners {
		font-size: clamp(1.25rem, 2.4vw, 1.55rem);
		font-weight: 400;
		font-style: italic;
		color: var(--rust-bright);
		letter-spacing: -0.005em;
	}

	@media (max-width: 540px) {
		.cost { padding-left: 1.1rem; }
		.row { grid-template-columns: minmax(3.3rem, auto) 1fr; gap: 0.85rem; }
		.ledger-inline { gap: 0.5rem 0.8rem; }
	}

	.prose {
		max-width: min(820px, 100%);
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
		max-width: min(820px, 100%);
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

	.emissions {
		margin-top: 1.6rem;
		padding: 1.4rem 1.4rem 1.1rem;
		max-width: min(820px, 100%);
	}
	.emissions-title {
		font-family: var(--serif);
		font-size: 1rem;
		font-weight: 300;
		color: var(--text-dim);
		margin-bottom: 0.9rem;
		letter-spacing: -0.005em;
	}
	/* <em> stays italic by browser default; no rust color bleed here so
	   hero styling (h2/h3/.sub) remains the sole owner of that palette. */
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
	}
</style>
