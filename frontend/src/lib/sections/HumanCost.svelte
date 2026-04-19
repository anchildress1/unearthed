<script>
	let { data } = $props();
</script>

<section class="cost">
	<div class="label">
		<span class="label-line"></span>
		<span class="label-text">03 &ensp; the cost</span>
	</div>

	{#if data.prose}
		<blockquote class="prose">{data.prose}</blockquote>
	{:else}
		<blockquote class="prose"><em>The earth does not grow back.</em></blockquote>
	{/if}

	<div class="details glass">
		<dl>
			<div class="row"><dt>Mine</dt><dd>{data.mine}</dd></div>
			<div class="row"><dt>Operator</dt><dd>{data.mine_operator}</dd></div>
			<div class="row"><dt>Type</dt><dd>{data.mine_type}</dd></div>
			<div class="row"><dt>Plant</dt><dd>{data.plant}</dd></div>
			<div class="row"><dt>Plant operator</dt><dd>{data.plant_operator}</dd></div>
			<div class="row"><dt>Tonnage</dt><dd>{Number(data.tons).toLocaleString()} tons ({data.tons_year})</dd></div>
		</dl>
	</div>
</section>

<style>
	.cost {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		justify-content: center;
		padding: var(--section-pad);
	}

	.label { display: flex; align-items: center; gap: 0.8rem; margin-bottom: 2rem; }
	.label-line { width: 32px; height: 1px; background: var(--text-ghost); }
	.label-text {
		font-family: var(--mono);
		font-size: 0.6rem;
		letter-spacing: 0.25em;
		text-transform: uppercase;
		color: var(--text-ghost);
	}

	.prose {
		font-family: var(--serif);
		font-size: clamp(1.15rem, 2.5vw, 1.45rem);
		font-weight: 300;
		line-height: 2;
		color: var(--text);
		max-width: 560px;
		margin-bottom: 3.5rem;
		border: none;
		padding: 0;
	}
	.prose em {
		color: var(--text-dim);
	}

	.details {
		max-width: 480px;
		padding: 1.5rem 1.8rem;
	}

	dl {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
	}

	.row {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 1.5rem;
	}

	dt {
		font-family: var(--mono);
		font-size: 0.6rem;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		color: var(--text-ghost);
		flex-shrink: 0;
	}

	dd {
		font-family: var(--serif);
		font-size: 0.9rem;
		color: var(--text-dim);
		text-align: right;
	}
</style>
