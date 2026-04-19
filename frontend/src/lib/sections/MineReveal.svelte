<script>
	let { data } = $props();
</script>

<section class="reveal">
	<p class="reveal__pre">02 — THE SOURCE</p>
	<h2 class="reveal__title">
		<em>{data.mine}</em>
	</h2>
	<p class="reveal__location">
		{data.mine_county}, {data.mine_state}
	</p>
	<p class="reveal__operator">{data.mine_operator}</p>

	<div class="reveal__stat">
		<span class="reveal__number">{Number(data.tons).toLocaleString()}</span>
		<span class="reveal__unit">tons of coal in {data.tons_year}</span>
	</div>

	<p class="reveal__verdict">
		From this mine. To <em>{data.plant}</em>. To your grid.
	</p>
</section>

<style>
	.reveal {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 4rem 2rem;
		text-align: center;
	}

	.reveal__pre {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.75rem;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		color: #8a8680;
		margin-bottom: 2rem;
	}

	.reveal__title {
		font-family: 'Playfair Display', serif;
		font-size: clamp(2rem, 6vw, 4.5rem);
		font-weight: 400;
		color: #d4d0c8;
		margin-bottom: 0.5rem;
	}

	.reveal__title em {
		color: #c4956a;
		font-style: italic;
	}

	.reveal__location {
		font-size: 1.1rem;
		color: #8a8680;
		margin-bottom: 0.25rem;
	}

	.reveal__operator {
		font-size: 0.9rem;
		color: #5a5650;
		margin-bottom: 3rem;
	}

	.reveal__stat {
		margin-bottom: 3rem;
	}

	.reveal__number {
		display: block;
		font-family: 'Playfair Display', serif;
		font-size: clamp(3rem, 10vw, 7rem);
		font-weight: 700;
		color: #c4956a;
		line-height: 1;
	}

	.reveal__unit {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.8rem;
		color: #8a8680;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}

	.reveal__verdict {
		font-family: 'Playfair Display', serif;
		font-size: clamp(1.2rem, 3vw, 1.8rem);
		color: #d4d0c8;
		max-width: 500px;
	}

	.reveal__verdict em {
		color: #8aaa8a;
		font-style: italic;
	}
</style>
