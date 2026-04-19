<script>
	import { fetchAsk } from '$lib/api.js';

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

<section class="cortex">
	<div class="header">
		<span class="badge">cortex analyst</span>
		<span class="live">● live</span>
	</div>

	<h3>Ask the data.</h3>
	<p class="sub">
		Powered by <strong>Snowflake Cortex Analyst</strong>. Your question becomes SQL.
		The SQL runs against federal mine safety records. The answer comes back with its source.
	</p>

	<div class="chips">
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
			placeholder="Ask anything about this mine, this plant, or your grid..."
			aria-label="Ask a question"
			maxlength="500"
			disabled={asking}
		/>
		<button type="submit" disabled={asking}>{asking ? '...' : 'Ask'}</button>
	</form>

	{#if transcript.length > 0}
		<div class="transcript">
			{#each transcript as entry}
				<div class="entry glass">
					<p class="q">{entry.question}</p>

					{#if entry.error}
						<p class="error">{entry.error}</p>
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

					{#if entry.sql}
						<details class="sql-details">
							<summary>Show SQL</summary>
							<pre>{entry.sql}</pre>
						</details>
					{/if}

					<div class="source">
						<span class="source-tag">source: MSHA + EIA federal records via Snowflake</span>
					</div>
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
	}

	.sub {
		font-family: var(--serif);
		font-size: 0.9rem;
		font-weight: 300;
		color: var(--text-dim);
		line-height: 1.7;
		margin-bottom: 1.5rem;
		max-width: 560px;
	}
	.sub strong {
		color: var(--accent);
		font-weight: 400;
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

	.transcript { display: flex; flex-direction: column; gap: 1rem; }

	.entry { padding: 1.2rem 1.4rem; }

	.q {
		font-family: var(--serif);
		font-weight: 600;
		font-size: 0.9rem;
		color: var(--accent);
		margin-bottom: 0.8rem;
	}

	.answer {
		font-family: var(--serif);
		font-size: 0.95rem;
		font-weight: 300;
		line-height: 1.8;
		color: var(--text);
		margin-bottom: 0.8rem;
	}

	.error {
		color: var(--accent);
		font-size: 0.85rem;
		font-style: italic;
		margin-bottom: 0.5rem;
	}

	.results { margin: 0.8rem 0; overflow-x: auto; }
	table { width: 100%; border-collapse: collapse; }
	th, td {
		text-align: left;
		padding: 0.4rem 0.6rem;
		border-bottom: 1px solid rgba(255,255,255,0.04);
		font-size: 0.8rem;
	}
	th {
		font-family: var(--mono);
		font-size: 0.55rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-ghost);
	}
	td { color: var(--text-dim); }

	.sql-details { margin-top: 0.5rem; }
	.sql-details summary {
		font-family: var(--mono);
		font-size: 0.65rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--accent);
		cursor: pointer;
		padding: 0.3rem 0;
	}
	.sql-details pre {
		margin-top: 0.5rem;
		padding: 0.8rem;
		background: rgba(0,0,0,0.4);
		border-radius: 6px;
		border: 1px solid rgba(255,255,255,0.03);
		font-family: var(--mono);
		font-size: 0.7rem;
		color: var(--accent);
		white-space: pre-wrap;
		word-break: break-word;
		line-height: 1.5;
		overflow-x: auto;
	}

	.source {
		margin-top: 0.6rem;
		padding-top: 0.5rem;
		border-top: 1px solid rgba(255,255,255,0.03);
	}
	.source-tag {
		font-family: var(--mono);
		font-size: 0.5rem;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		color: var(--text-ghost);
	}
</style>
