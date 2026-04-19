<script>
	let { data } = $props();

	let paragraphs = $derived(
		(data.prose || '').split(/\n\n+/).filter(Boolean)
	);
</script>

<section class="reveal">
	<h2>
		Your <em>kilowatt-hour</em><br/>starts here.
	</h2>

	<div class="prose">
		{#each paragraphs as para}
			<p>{para}</p>
		{/each}
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
</style>
