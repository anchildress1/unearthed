<script>
	let { data } = $props();
</script>

<section class="cost">
	<p class="cost__pre">03 — THE COST</p>

	{#if data.prose}
		<div class="cost__prose">{data.prose}</div>
	{:else}
		<h2 class="cost__fallback">The earth does not grow back.</h2>
	{/if}

	<div class="cost__grid">
		<dl class="cost__details">
			<dt>Mine</dt><dd>{data.mine}</dd>
			<dt>Operator</dt><dd>{data.mine_operator}</dd>
			<dt>Type</dt><dd>{data.mine_type}</dd>
			<dt>Plant</dt><dd>{data.plant}</dd>
			<dt>Plant operator</dt><dd>{data.plant_operator}</dd>
			<dt>Annual tonnage</dt><dd>{Number(data.tons).toLocaleString()} tons ({data.tons_year})</dd>
		</dl>
	</div>
</section>

<style>
	.cost {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 4rem 2rem;
	}

	.cost__pre {
		font-family: var(--font-mono);
		font-size: 0.7rem;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		color: var(--text-muted);
		margin-bottom: 3rem;
	}

	.cost__prose {
		font-family: var(--font-serif);
		font-size: clamp(1.1rem, 2.5vw, 1.4rem);
		line-height: 1.9;
		color: var(--text);
		max-width: 580px;
		margin-bottom: 4rem;
		text-align: left;
	}

	.cost__fallback {
		font-family: var(--font-serif);
		font-size: clamp(1.5rem, 4vw, 2.5rem);
		font-weight: 400;
		font-style: italic;
		color: var(--text-muted);
		margin-bottom: 3rem;
		max-width: 600px;
		text-align: center;
	}

	.cost__grid {
		max-width: 500px;
		width: 100%;
		padding: 1.5rem;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 4px;
	}

	.cost__details {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.6rem 2rem;
	}

	.cost__details dt {
		font-family: var(--font-mono);
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--text-muted);
		padding-top: 0.15rem;
	}

	.cost__details dd {
		font-size: 0.9rem;
		color: var(--text);
	}
</style>
