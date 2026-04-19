<script>
	let { data } = $props();
</script>

<section class="reveal">
	<p class="reveal__pre">02 — THE SOURCE</p>
	<h2 class="reveal__title">
		<em>{data.mine}</em>
	</h2>
	<p class="reveal__location">{data.mine_county}, {data.mine_state}</p>
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
		font-family: var(--font-mono);
		font-size: 0.7rem;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		color: var(--text-muted);
		margin-bottom: 2rem;
	}

	.reveal__title {
		font-family: var(--font-serif);
		font-size: clamp(2rem, 6vw, 4.5rem);
		font-weight: 400;
		color: var(--text);
		margin-bottom: 0.5rem;
	}

	.reveal__title em { color: var(--accent); font-style: italic; }

	.reveal__location { font-size: 1.1rem; color: var(--text-muted); margin-bottom: 0.25rem; }
	.reveal__operator { font-size: 0.85rem; color: #4a4540; margin-bottom: 3rem; }

	.reveal__stat { margin-bottom: 3rem; }

	.reveal__number {
		display: block;
		font-family: var(--font-serif);
		font-size: clamp(3rem, 10vw, 7rem);
		font-weight: 400;
		color: var(--accent);
		line-height: 1;
	}

	.reveal__unit {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		color: var(--text-muted);
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}

	.reveal__verdict {
		font-family: var(--font-serif);
		font-size: clamp(1.2rem, 3vw, 1.8rem);
		color: var(--text);
		max-width: 500px;
	}

	.reveal__verdict em { color: var(--green); font-style: italic; }
</style>
