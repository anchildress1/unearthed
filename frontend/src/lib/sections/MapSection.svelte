<script>
	let { data } = $props();
</script>

<section class="map-section">
	<p class="map-section__pre">— THE CHAIN</p>
	<div class="map-section__container" id="map-container">
		<!-- Google Maps will mount here -->
		<p class="map-section__placeholder">Map loading...</p>
	</div>
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
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.75rem;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		color: #8a8680;
		margin-bottom: 1.5rem;
	}

	.map-section__container {
		width: 100%;
		max-width: 1000px;
		height: 500px;
		background: #141414;
		border: 1px solid #2a2725;
		border-radius: 6px;
		overflow: hidden;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.map-section__placeholder {
		color: #8a8680;
		font-size: 0.9rem;
	}
</style>
