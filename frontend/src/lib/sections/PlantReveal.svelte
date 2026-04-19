<script>
	import { onMount } from 'svelte';
	import { fetchEmissions } from '$lib/api.js';
	import { reveal } from '$lib/reveal.js';

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
</script>

<section class="reveal" use:reveal={{ distance: 18 }}>
	<h2>
		Your <em>kilowatt-hour</em><br/>starts here.
	</h2>

	<div class="prose">
		{#if data.prose}
			{#each data.prose.split(/\n{2,}/) as paragraph}
				{#if paragraph.trim()}
					<p>{paragraph.trim()}</p>
				{/if}
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
			<span class="card-label">tons shipped, {data.tons_year}</span>
		</div>
		<div class="card glass">
			<span class="card-value">{data.subregion_id}</span>
			<span class="card-label">eGRID subregion</span>
		</div>
		<div class="card glass">
			<span class="card-value">{data.mine_type}</span>
			<span class="card-label">mine type</span>
		</div>
	</div>

	{#if emissions}
		<div class="emissions glass" aria-label="Plant emissions">
			<p class="emissions-title">
				Burning that coal <em>releases</em>
			</p>
			<div class="emissions-cards">
				<div class="e-card">
					<span class="e-value rust">{formatTons(emissions.co2_tons)}</span>
					<span class="e-label">short tons CO<sub>2</sub></span>
				</div>
				<div class="e-card">
					<span class="e-value">{formatTons(emissions.so2_tons)}</span>
					<span class="e-label">short tons SO<sub>2</sub></span>
				</div>
				<div class="e-card">
					<span class="e-value">{formatTons(emissions.nox_tons)}</span>
					<span class="e-label">short tons NO<sub>x</sub></span>
				</div>
			</div>
			<p class="emissions-source">
				EPA Clean Air Markets, 2020–present · <strong>Snowflake Marketplace</strong>
			</p>
		</div>
	{/if}
</section>

<style>
	.reveal {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		justify-content: center;
		padding: var(--section-pad);
		max-width: 900px;
		margin: 0 auto;
	}

	h2 {
		font-family: var(--serif);
		font-size: clamp(2.5rem, 6vw, 4.5rem);
		font-weight: 400;
		line-height: 1.1;
		color: var(--text);
		margin-bottom: 2rem;
	}
	h2 em { color: var(--accent); font-style: italic; }

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
	.prose strong {
		color: var(--text);
		font-weight: 400;
	}
	.prose :global(.rust) { color: var(--accent); }

	.cards {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
		gap: 0.8rem;
		max-width: 600px;
	}

	.card {
		padding: 1.2rem;
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}

	.card-value {
		font-family: var(--serif);
		font-size: 1.5rem;
		font-weight: 400;
		color: var(--text);
	}
	.card-value.rust { color: var(--accent); }

	.card-label {
		font-family: var(--mono);
		font-size: 0.55rem;
		text-transform: uppercase;
		letter-spacing: 0.15em;
		color: var(--text-ghost);
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
		color: var(--accent);
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
		gap: 0.15rem;
		padding: 0.5rem 0.6rem;
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
	.e-value.rust { color: var(--accent); }
	.e-label {
		font-family: var(--mono);
		font-size: 0.52rem;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		color: var(--text-ghost);
	}
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
		color: var(--accent);
		font-weight: 400;
	}

	@media (max-width: 540px) {
		.emissions-cards { grid-template-columns: 1fr 1fr; }
		.e-card:nth-child(3) { border-left: none; padding-left: 0; }
	}
</style>
