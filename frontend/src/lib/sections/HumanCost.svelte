<script>
	let { data } = $props();
</script>

<section class="cost">
	<p class="cost__pre">03 — THE COST</p>

	{#if data.prose}
		<div class="cost__prose">
			{data.prose}
		</div>
	{:else}
		<h2 class="cost__title">
			The earth does not grow back.
		</h2>
	{/if}

	<div class="cost__details">
		<div class="cost__detail">
			<span class="cost__label">Mine</span>
			<span class="cost__value">{data.mine}</span>
		</div>
		<div class="cost__detail">
			<span class="cost__label">Operator</span>
			<span class="cost__value">{data.mine_operator}</span>
		</div>
		<div class="cost__detail">
			<span class="cost__label">Type</span>
			<span class="cost__value">{data.mine_type}</span>
		</div>
		<div class="cost__detail">
			<span class="cost__label">Plant</span>
			<span class="cost__value">{data.plant} ({data.plant_operator})</span>
		</div>
		<div class="cost__detail">
			<span class="cost__label">Annual tonnage</span>
			<span class="cost__value">{Number(data.tons).toLocaleString()} tons ({data.tons_year})</span>
		</div>
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
		text-align: center;
	}

	.cost__pre {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.75rem;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		color: #8a8680;
		margin-bottom: 3rem;
	}

	.cost__title {
		font-family: 'Playfair Display', serif;
		font-size: clamp(1.5rem, 4vw, 2.5rem);
		font-weight: 400;
		font-style: italic;
		color: #8a8680;
		margin-bottom: 3rem;
		max-width: 600px;
	}

	.cost__prose {
		font-family: 'Playfair Display', serif;
		font-size: clamp(1.1rem, 2.5vw, 1.5rem);
		line-height: 1.8;
		color: #d4d0c8;
		max-width: 600px;
		margin-bottom: 4rem;
		text-align: left;
	}

	.cost__details {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.75rem 2rem;
		text-align: left;
		max-width: 500px;
		width: 100%;
		padding: 1.5rem;
		background: #141414;
		border: 1px solid #2a2725;
		border-radius: 6px;
	}

	.cost__detail {
		display: contents;
	}

	.cost__label {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: #8a8680;
		padding-top: 0.1rem;
	}

	.cost__value {
		font-size: 0.95rem;
		color: #d4d0c8;
	}
</style>
