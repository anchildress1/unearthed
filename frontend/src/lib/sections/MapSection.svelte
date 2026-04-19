<script>
	let { data } = $props();
</script>

<section class="map-section">
	<p class="map-section__pre">— THE CHAIN</p>
	<div class="map-section__container" id="map-container">
		<p class="map-section__placeholder">Map loading...</p>
	</div>
	<p class="map-section__caption">
		{data.mine} → {data.plant} → your grid
	</p>
</section>

<style>
	.map-section {
		min-height: 80vh;
		padding: 2rem;
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.map-section__pre {
		font-family: var(--font-mono);
		font-size: 0.7rem;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		color: var(--text-muted);
		margin-bottom: 1.5rem;
	}

	.map-section__container {
		width: 100%;
		max-width: 1000px;
		height: 500px;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 4px;
		overflow: hidden;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.map-section__placeholder {
		color: var(--text-muted);
		font-size: 0.9rem;
	}

	.map-section__caption {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		color: var(--text-muted);
		margin-top: 1rem;
		letter-spacing: 0.05em;
	}
</style>
