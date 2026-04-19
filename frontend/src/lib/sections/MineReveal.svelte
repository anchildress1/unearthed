<script>
	let { data } = $props();
</script>

<section class="reveal">
	<h2><em>{data.mine}.</em></h2>
	<p class="geo">{data.mine_county}, {data.mine_state}</p>
	<p class="operator">{data.mine_operator}</p>

	<div class="tonnage">
		<span class="tons">{Number(data.tons).toLocaleString()}</span>
		<span class="tons-label">tons of coal shipped to your grid, {data.tons_year}</span>
	</div>

	<p class="verdict">
		From this <em class="rust">coal mine</em>. To the <em class="rust">{data.plant}</em> power plant. To you.
	</p>
</section>

<style>
	.reveal {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--section-pad);
		text-align: center;
	}

	h2 {
		font-family: var(--serif);
		font-size: clamp(2.5rem, 7vw, 5rem);
		font-weight: 400;
		line-height: 1.05;
		color: var(--text);
		margin-bottom: 0.6rem;
	}
	h2 em { font-style: italic; color: var(--accent); }

	.geo { font-size: 1.1rem; color: var(--text-dim); margin-bottom: 0.2rem; }
	.operator { font-size: 0.85rem; color: var(--text-ghost); margin-bottom: 3.5rem; }

	.tonnage { margin-bottom: 3.5rem; text-align: center; }
	.tons {
		display: block;
		font-family: var(--serif);
		font-size: clamp(3.5rem, 12vw, 8rem);
		font-weight: 300;
		color: var(--accent);
		line-height: 0.95;
		letter-spacing: -0.02em;
	}
	.tons-label {
		font-family: var(--mono);
		font-size: 0.65rem;
		color: var(--text-ghost);
		letter-spacing: 0.12em;
		text-transform: uppercase;
		margin-top: 0.5rem;
		display: block;
	}

	.verdict {
		font-family: var(--serif);
		font-size: clamp(1.2rem, 3vw, 1.8rem);
		font-weight: 300;
		color: var(--text-dim);
		max-width: 520px;
		line-height: 1.5;
	}
	.verdict :global(.rust) { color: var(--accent); }
</style>
