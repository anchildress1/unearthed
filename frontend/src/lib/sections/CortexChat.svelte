<script>
	import { fetchAsk } from '$lib/api.js';
	import { reveal } from '$lib/reveal.js';

	const props = $props();
	let question = $state('');
	let transcript = $state([]);
	let asking = $state(false);

	const chips = $derived([
		`How much has ${props.mineName} produced since 2020?`,
		`Which mines supplied ${props.plantName} in 2024? Rank by tonnage.`,
		`Is ${props.mineName} still active?`,
		`How many fatalities at ${props.mineName}?`,
		'Who is the largest coal supplier in this state?',
	]);

	async function ask(q) {
		if (asking || !q.trim()) return;
		asking = true;
		console.log('[unearthed] cortex query:', q);
		const entry = { question: q, answer: null, error: null, sql: null, results: null };
		transcript = [...transcript, entry];
		question = '';
		try {
			const result = await fetchAsk(q, props.subregionId);
			entry.answer = result.answer || result.interpretation || '';
			entry.sql = result.sql;
			entry.error = result.error;
			entry.results = result.results;
			transcript = [...transcript];
			console.log('[unearthed] cortex response:', entry.answer?.slice(0, 100));
		} catch (e) {
			console.error('[unearthed] cortex error:', e);
			entry.error = 'Could not reach the data assistant.';
			transcript = [...transcript];
		} finally {
			asking = false;
		}
	}

	function handleSubmit(e) {
		e.preventDefault();
		ask(question);
	}
</script>

<section class="cortex" use:reveal>
	<div class="header">
		<span class="badge">snowflake cortex analyst</span>
		<span class="live" aria-label="Live connection">● live</span>
	</div>

	<h3>Interrogate the <em>records</em>.</h3>
	<p class="sub">
		Your question becomes <strong>SQL</strong>. The SQL runs against federal mine data
		pooled in Snowflake. The answer comes back with the generated query attached —
		<em>honesty, not hallucination</em>.
	</p>

	<div class="pipeline" aria-hidden="true">
		<span class="p-step"><span class="p-num">01</span> natural language</span>
		<span class="p-arrow">→</span>
		<span class="p-step"><span class="p-num">02</span> generated SQL</span>
		<span class="p-arrow">→</span>
		<span class="p-step"><span class="p-num">03</span> federal data</span>
	</div>

	<div class="chips" role="list" aria-label="Suggested questions">
		{#each chips as chip}
			<button class="chip" onclick={() => ask(chip)} disabled={asking}>{chip}</button>
		{/each}
	</div>

	<form class="form glass" onsubmit={handleSubmit}>
		<input
			id="chat-input"
			name="question"
			type="text"
			bind:value={question}
			placeholder="Ask anything about this mine, this plant, or your grid…"
			aria-label="Ask a question"
			maxlength="500"
			disabled={asking}
		/>
		<button type="submit" disabled={asking}>{asking ? 'asking…' : 'ask →'}</button>
	</form>

	{#if transcript.length > 0}
		<div class="transcript">
			{#each transcript as entry}
				<div class="entry glass">
					<div class="stage">
						<span class="stage-num">01</span>
						<span class="stage-label">question</span>
					</div>
					<p class="q">{entry.question}</p>

					{#if entry.error}
						<div class="stage err-stage">
							<span class="stage-num">!!</span>
							<span class="stage-label">couldn't answer</span>
						</div>
						<p class="error">{entry.error}</p>
					{/if}

					{#if entry.sql}
						<div class="stage">
							<span class="stage-num">02</span>
							<span class="stage-label">generated SQL · Cortex Analyst</span>
						</div>
						<pre class="sql-pre">{entry.sql}</pre>
					{/if}

					{#if entry.answer || (entry.results && entry.results.length > 0)}
						<div class="stage">
							<span class="stage-num">03</span>
							<span class="stage-label">federal data · MSHA + EIA</span>
						</div>
					{/if}

					{#if entry.answer}
						<p class="answer">{entry.answer}</p>
					{/if}

					{#if entry.results && entry.results.length === 0}
						<p class="no-results">Query ran successfully but returned no rows.</p>
					{:else if entry.results && entry.results.length > 0}
						<div class="results">
							<table>
								<thead>
									<tr>
										{#each Object.keys(entry.results[0]) as col}
											<th>{col.replace(/_/g, ' ')}</th>
										{/each}
									</tr>
								</thead>
								<tbody>
									{#each entry.results as row}
										<tr>
											{#each Object.values(row) as val}
												<td>{typeof val === 'number' ? val.toLocaleString() : val}</td>
											{/each}
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</section>

<style>
	.cortex {
		padding: var(--section-pad);
		max-width: 740px;
		margin: 0 auto;
	}

	.header {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-bottom: 1rem;
	}

	.badge {
		font-family: var(--mono);
		font-size: 0.6rem;
		text-transform: uppercase;
		letter-spacing: 0.2em;
		color: var(--accent);
		border: 1px solid rgba(194,84,45,0.3);
		padding: 0.25rem 0.6rem;
		border-radius: 3px;
	}

	.live {
		font-family: var(--mono);
		font-size: 0.55rem;
		text-transform: uppercase;
		letter-spacing: 0.15em;
		color: var(--green);
	}

	h3 {
		font-family: var(--serif);
		font-size: clamp(2rem, 4vw, 3rem);
		font-weight: 400;
		color: var(--text);
		margin-bottom: 0.5rem;
		letter-spacing: -0.01em;
	}
	h3 em { color: var(--accent); font-style: italic; }

	.sub {
		font-family: var(--serif);
		font-size: 0.95rem;
		font-weight: 300;
		color: var(--text-dim);
		line-height: 1.75;
		margin-bottom: 1.4rem;
		max-width: 580px;
	}
	.sub strong {
		color: var(--text);
		font-weight: 400;
	}
	.sub em {
		color: var(--accent);
		font-style: italic;
	}

	.pipeline {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.7rem;
		margin-bottom: 1.4rem;
		font-family: var(--mono);
		font-size: 0.55rem;
		text-transform: uppercase;
		letter-spacing: 0.16em;
		color: var(--text-ghost);
	}
	.p-step {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.3rem 0.55rem;
		border: 1px solid rgba(255, 255, 255, 0.06);
		border-radius: 3px;
		background: rgba(255, 255, 255, 0.015);
	}
	.p-num {
		color: var(--accent);
		font-weight: 400;
	}
	.p-arrow {
		color: var(--text-ghost);
		font-size: 0.8rem;
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-bottom: 1.2rem;
	}
	.chip {
		font-family: var(--serif);
		font-size: 0.8rem;
		font-style: italic;
		padding: 0.45rem 0.9rem;
		background: rgba(255,255,255,0.02);
		border: 1px solid var(--border-glass);
		border-radius: 2rem;
		color: var(--text-dim);
		cursor: pointer;
		transition: all 0.2s;
	}
	.chip:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
	.chip:disabled { opacity: 0.3; cursor: not-allowed; }

	.form {
		display: flex;
		gap: 0.5rem;
		padding: 0.7rem;
		margin-bottom: 1.5rem;
	}

	input[type="text"] {
		flex: 1;
		font-family: var(--serif);
		font-size: 0.9rem;
		padding: 0.7rem 0.9rem;
		background: rgba(0,0,0,0.3);
		color: var(--text);
		border: 1px solid rgba(255,255,255,0.05);
		border-radius: 6px;
		outline: none;
	}
	input:focus { border-color: var(--accent); }
	input::placeholder { color: var(--text-ghost); font-style: italic; }

	button[type="submit"] {
		font-family: var(--mono);
		font-size: 0.7rem;
		padding: 0.7rem 1rem;
		background: var(--accent);
		color: #fff;
		border: none;
		border-radius: 6px;
		cursor: pointer;
		letter-spacing: 0.08em;
	}
	button[type="submit"]:disabled { opacity: 0.3; cursor: not-allowed; }

	.transcript { display: flex; flex-direction: column; gap: 1.2rem; }

	.entry { padding: 1.3rem 1.5rem; }

	.stage {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		margin-top: 0.9rem;
		margin-bottom: 0.4rem;
	}
	.stage:first-child { margin-top: 0; }
	.stage-num {
		font-family: var(--mono);
		font-size: 0.6rem;
		color: var(--accent);
		letter-spacing: 0.12em;
		font-weight: 400;
	}
	.stage-label {
		font-family: var(--mono);
		font-size: 0.5rem;
		text-transform: uppercase;
		letter-spacing: 0.2em;
		color: var(--text-ghost);
	}
	.err-stage .stage-num { color: var(--accent); }

	.q {
		font-family: var(--serif);
		font-weight: 400;
		font-style: italic;
		font-size: 1.05rem;
		color: var(--text);
		line-height: 1.5;
		margin-bottom: 0.2rem;
	}

	.answer {
		font-family: var(--serif);
		font-size: 0.98rem;
		font-weight: 300;
		line-height: 1.8;
		color: var(--text);
		margin-bottom: 0.4rem;
	}

	.error {
		color: var(--accent);
		font-size: 0.85rem;
		font-style: italic;
	}

	.no-results {
		font-family: var(--mono);
		font-size: 0.7rem;
		color: var(--text-ghost);
		font-style: italic;
	}

	.results { margin: 0.4rem 0 0.2rem; overflow-x: auto; }
	table { width: 100%; border-collapse: collapse; }
	th, td {
		text-align: left;
		padding: 0.45rem 0.7rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.04);
		font-size: 0.82rem;
	}
	th {
		font-family: var(--mono);
		font-size: 0.55rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-ghost);
		font-weight: 400;
	}
	td { color: var(--text-dim); font-family: var(--serif); }

	.sql-pre {
		margin: 0;
		padding: 0.9rem 1rem;
		background: rgba(0, 0, 0, 0.45);
		border-radius: 6px;
		border-left: 2px solid var(--accent);
		font-family: var(--mono);
		font-size: 0.72rem;
		color: var(--accent);
		white-space: pre-wrap;
		word-break: break-word;
		line-height: 1.55;
		overflow-x: auto;
	}
</style>
