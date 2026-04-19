<script>
	let { data } = $props();
</script>

<section class="map">
	<div class="map-frame glass">
		<div class="map-container" id="map-container">
			<p class="placeholder">Map loading...</p>
		</div>
	</div>
	<p class="chain">
		{data.mine} <span class="arrow">→</span> {data.plant} <span class="arrow">→</span> your grid
	</p>
</section>

<style>
	.map {
		padding: var(--section-pad);
		padding-top: 2rem;
		padding-bottom: 2rem;
	}

	.map-frame {
		width: 100%;
		max-width: 1000px;
		overflow: hidden;
		padding: 0;
	}

	.map-container {
		width: 100%;
		height: clamp(350px, 50vh, 550px);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.placeholder {
		font-family: var(--mono);
		font-size: 0.75rem;
		color: var(--text-ghost);
		letter-spacing: 0.1em;
	}

	.chain {
		font-family: var(--mono);
		font-size: 0.65rem;
		color: var(--text-ghost);
		letter-spacing: 0.08em;
		margin-top: 1rem;
	}
	.arrow { color: var(--accent); }
</style>
