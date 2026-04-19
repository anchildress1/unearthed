<script>
	let { data } = $props();
</script>

<section class="cost">
	{#if data.prose}
		<blockquote class="prose">{data.prose}</blockquote>
	{:else}
		<blockquote class="prose"><em>The earth does not grow back.</em></blockquote>
	{/if}

	<div class="details glass">
		<dl>
			<div class="row"><dt>Coal mine</dt><dd>{data.mine}</dd></div>
			<div class="row"><dt>Mine operator</dt><dd>{data.mine_operator}</dd></div>
			<div class="row"><dt>Mine type</dt><dd>{data.mine_type}</dd></div>
			<div class="row"><dt>Power plant</dt><dd>{data.plant}</dd></div>
			<div class="row"><dt>Plant operator</dt><dd>{data.plant_operator}</dd></div>
			<div class="row"><dt>Coal shipped</dt><dd>{Number(data.tons).toLocaleString()} tons ({data.tons_year})</dd></div>
		</dl>
	</div>
</section>

<style>
	.cost {
		min-height: 80vh;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--section-pad);
		text-align: center;
	}

	.prose {
		font-family: var(--serif);
		font-size: clamp(1.15rem, 2.5vw, 1.45rem);
		font-weight: 300;
		line-height: 2;
		color: var(--text);
		max-width: 560px;
		margin-bottom: 3rem;
		border: none;
		padding: 0;
		text-align: left;
	}
	.prose em { color: var(--text-dim); }

	.details {
		max-width: 480px;
		width: 100%;
		padding: 1.5rem 1.8rem;
	}

	dl { display: flex; flex-direction: column; gap: 0.6rem; }

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
