<script>
	let { loading, error, onTrace } = $props();
	let address = $state('');

	function handleSubmit(e) {
		e.preventDefault();
		if (!address.trim()) return;
		// For now, hardcode SRVC — geocoding will come later
		onTrace('SRVC');
	}
</script>

<section class="hero">
	<div class="hero__content">
		<p class="hero__pre">01 — THE SWITCH</p>
		<h1 class="hero__title">
			You came home.<br />
			You turned on <em>a light.</em>
		</h1>

		<p class="hero__sub">tell us where that light is</p>

		<form class="hero__form" onsubmit={handleSubmit}>
			<input
				class="hero__input"
				type="text"
				placeholder="Enter address or zip code"
				bind:value={address}
				maxlength="200"
				autocomplete="off"
			/>
			<button class="hero__btn" type="submit" disabled={loading}>
				{loading ? '...' : 'Trace →'}
			</button>
		</form>

		{#if error}
			<p class="hero__error">{error}</p>
		{/if}

		<p class="hero__scroll">↓ scroll slowly</p>
	</div>
</section>

<style>
	.hero {
		min-height: 100vh;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 2rem;
		position: relative;
	}

	.hero__content {
		text-align: center;
		max-width: 700px;
	}

	.hero__pre {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.75rem;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		color: #8a8680;
		margin-bottom: 2rem;
	}

	.hero__title {
		font-family: 'Playfair Display', serif;
		font-size: clamp(2.5rem, 7vw, 5rem);
		font-weight: 400;
		line-height: 1.1;
		color: #d4d0c8;
		margin-bottom: 3rem;
	}

	.hero__title em {
		color: #c4956a;
		font-style: italic;
	}

	.hero__sub {
		font-size: 0.85rem;
		color: #8a8680;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		margin-bottom: 1.5rem;
	}

	.hero__form {
		display: flex;
		gap: 0.5rem;
		max-width: 480px;
		margin: 0 auto 2rem;
	}

	.hero__input {
		flex: 1;
		font-family: 'Inter', sans-serif;
		font-size: 1rem;
		padding: 0.85rem 1.2rem;
		background: #1a1a1a;
		color: #d4d0c8;
		border: 1px solid #2a2725;
		border-radius: 4px;
	}

	.hero__input:focus {
		outline: none;
		border-color: #c4956a;
	}

	.hero__input::placeholder {
		color: #8a8680;
	}

	.hero__btn {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.85rem;
		padding: 0.85rem 1.5rem;
		background: transparent;
		color: #c4956a;
		border: 1px solid #c4956a;
		border-radius: 4px;
		cursor: pointer;
		letter-spacing: 0.05em;
		white-space: nowrap;
	}

	.hero__btn:hover:not(:disabled) {
		background: #c4956a;
		color: #0a0a0a;
	}

	.hero__btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.hero__error {
		color: #c45a5a;
		font-size: 0.9rem;
		margin-bottom: 1rem;
	}

	.hero__scroll {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.75rem;
		color: #8a8680;
		letter-spacing: 0.1em;
		position: absolute;
		bottom: 2rem;
		left: 50%;
		transform: translateX(-50%);
	}
</style>
