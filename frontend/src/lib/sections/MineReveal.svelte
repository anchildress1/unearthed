<script>
	let { data } = $props();
</script>

<section class="reveal">
	<div class="label">
		<span class="label-line"></span>
		<span class="label-text">02 &ensp; the source</span>
	</div>

	<h2><em>{data.mine}.</em></h2>

	<p class="geo">{data.mine_county}, {data.mine_state}</p>
	<p class="operator">{data.mine_operator}</p>

	<div class="tonnage">
		<span class="tons">{Number(data.tons).toLocaleString()}</span>
		<span class="tons-label">tons of coal, {data.tons_year}</span>
	</div>

	<p class="verdict">
		From this mine. To <em class="rust">{data.plant}</em>. To your grid.
	</p>
</section>

<style>
	.reveal {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		justify-content: center;
		padding: var(--section-pad);
	}

	.label { display: flex; align-items: center; gap: 0.8rem; margin-bottom: 1.8rem; }
	.label-line { width: 32px; height: 1px; background: var(--text-ghost); }
	.label-text {
		font-family: var(--mono);
		font-size: 0.6rem;
		letter-spacing: 0.25em;
		text-transform: uppercase;
		color: var(--text-ghost);
	}

	h2 {
		font-family: var(--serif);
		font-size: clamp(2.5rem, 7vw, 5rem);
		font-weight: 400;
		line-height: 1.05;
		color: var(--text);
		margin-bottom: 0.6rem;
	}
	h2 em {
		font-style: italic;
		color: var(--accent);
	}

	.geo {
		font-size: 1.1rem;
		color: var(--text-dim);
		margin-bottom: 0.2rem;
	}
	.operator {
		font-size: 0.85rem;
		color: var(--text-ghost);
		margin-bottom: 3.5rem;
	}

	.tonnage {
		margin-bottom: 3.5rem;
	}
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
		letter-spacing: 0.15em;
		text-transform: uppercase;
		margin-top: 0.4rem;
		display: block;
	}

	.verdict {
		font-family: var(--serif);
		font-size: clamp(1.3rem, 3vw, 2rem);
		font-weight: 300;
		color: var(--text-dim);
		max-width: 500px;
		line-height: 1.4;
	}
	.verdict :global(.rust) {
		color: var(--accent);
	}
</style>
