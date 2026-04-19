<script>
	import { fetchAsk } from '$lib/api.js';

	let { subregionId, mineName } = $props();
	let question = $state('');
	let transcript = $state([]);
	let asking = $state(false);

	const chips = [
		`How much has ${mineName} produced since 2020?`,
		`Is ${mineName} still active?`,
		'Who is the largest coal supplier in this state?',
		'How many fatalities at this mine?',
	];

	async function ask(q) {
		if (asking || !q.trim()) return;
		asking = true;
		console.log('[unearthed] asking Cortex:', q);
		const entry = { question: q, answer: null, error: null, sql: null };
		transcript = [...transcript, entry];
		question = '';
		try {
			const result = await fetchAsk(q, subregionId);
			entry.answer = result.answer || result.interpretation || '';
			entry.sql = result.sql;
			entry.error = result.error;
			entry.results = result.results;
			transcript = [...transcript];
			console.log('[unearthed] Cortex answered:', entry.answer?.slice(0, 80));
		} catch (e) {
			console.error('[unearthed] Cortex failed:', e);
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

<section class="chat">
	<h3 class="chat-heading">Ask the data</h3>
	<p class="chat-sub">
		Powered by <strong>Snowflake Cortex Analyst</strong> — ask anything about this mine, its operators, or your grid.
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
			placeholder="Ask a question about this mine..."
			aria-label="Ask a question about this mine"
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
						<p class="a">{entry.answer}</p>
					{/if}
					{#if entry.results && entry.results.length > 0}
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
						<details>
							<summary class="sql-toggle">Show generated SQL</summary>
							<pre class="sql">{entry.sql}</pre>
						</details>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</section>

<style>
	.chat {
		min-height: 80vh;
		padding: var(--section-pad);
		max-width: 700px;
		margin: 0 auto;
	}

	.chat-heading {
		font-family: var(--serif);
		font-size: clamp(1.8rem, 4vw, 2.5rem);
		font-weight: 400;
		color: var(--text);
		margin-bottom: 0.5rem;
		text-align: center;
	}

	.chat-sub {
		font-family: var(--serif);
		font-size: 0.9rem;
		color: var(--text-dim);
		text-align: center;
		margin-bottom: 2rem;
		font-style: italic;
	}
	.chat-sub strong {
		color: var(--accent);
		font-weight: 600;
		font-style: normal;
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-bottom: 1.2rem;
		justify-content: center;
	}
	.chip {
		font-family: var(--serif);
		font-size: 0.8rem;
		font-style: italic;
		padding: 0.5rem 1rem;
		background: rgba(255,255,255,0.03);
		border: 1px solid var(--border-glass);
		border-radius: 2rem;
		color: var(--text-dim);
		cursor: pointer;
		transition: all 0.2s;
	}
	.chip:hover:not(:disabled) {
		border-color: var(--accent);
		color: var(--accent);
	}
	.chip:disabled { opacity: 0.4; cursor: not-allowed; }

	.form {
		display: flex;
		gap: 0.5rem;
		padding: 0.8rem;
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
		color: #ffffff;
		border: none;
		border-radius: 6px;
		cursor: pointer;
		letter-spacing: 0.08em;
	}
	button[type="submit"]:hover:not(:disabled) { opacity: 0.85; }
	button[type="submit"]:disabled { opacity: 0.4; cursor: not-allowed; }

	.transcript {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.entry { padding: 1.2rem; }

	.q {
		font-family: var(--serif);
		font-weight: 600;
		font-size: 0.9rem;
		color: var(--accent);
		margin-bottom: 0.6rem;
	}
	.a {
		font-size: 0.9rem;
		line-height: 1.7;
		color: var(--text);
	}
	.error {
		color: var(--accent);
		font-size: 0.85rem;
		font-style: italic;
	}

	.results {
		margin-top: 0.6rem;
		overflow-x: auto;
	}
	table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
	th, td {
		text-align: left;
		padding: 0.35rem 0.6rem;
		border-bottom: 1px solid rgba(255,255,255,0.05);
	}
	th {
		font-family: var(--mono);
		font-size: 0.6rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--text-ghost);
	}
	td { color: var(--text-dim); }

	.sql-toggle {
		font-family: var(--mono);
		font-size: 0.7rem;
		color: var(--green);
		cursor: pointer;
		margin-top: 0.5rem;
	}
	.sql {
		margin-top: 0.4rem;
		padding: 0.6rem;
		background: rgba(0,0,0,0.3);
		border-radius: 6px;
		font-family: var(--mono);
		font-size: 0.7rem;
		color: var(--green);
		white-space: pre-wrap;
		word-break: break-word;
	}
</style>
