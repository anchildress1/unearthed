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
	];

	async function ask(q) {
		if (asking || !q.trim()) return;
		asking = true;
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
		} catch {
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
	<p class="chat__pre">05 — ASK YOUR GRID</p>

	<div class="chat__chips">
		{#each chips as chip}
			<button class="chat__chip" onclick={() => ask(chip)} disabled={asking}>
				{chip}
			</button>
		{/each}
	</div>

	<form class="chat__form" onsubmit={handleSubmit}>
		<input
			class="chat__input"
			type="text"
			bind:value={question}
			placeholder="Ask a question about this mine..."
			maxlength="500"
			disabled={asking}
		/>
		<button class="chat__btn" type="submit" disabled={asking}>Ask</button>
	</form>

	<div class="chat__transcript">
		{#each transcript as entry}
			<div class="chat__entry">
				<p class="chat__q">{entry.question}</p>
				{#if entry.error}
					<p class="chat__error">{entry.error}</p>
				{/if}
				{#if entry.answer}
					<p class="chat__a">{entry.answer}</p>
				{/if}
				{#if entry.results}
					<div class="chat__results">
						<table>
							<thead>
								<tr>
									{#each Object.keys(entry.results[0] || {}) as col}
										<th>{col}</th>
									{/each}
								</tr>
							</thead>
							<tbody>
								{#each entry.results as row}
									<tr>
										{#each Object.values(row) as val}
											<td>{val}</td>
										{/each}
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
				{#if entry.sql}
					<details class="chat__sql-details">
						<summary class="chat__sql-toggle">Show SQL</summary>
						<pre class="chat__sql">{entry.sql}</pre>
					</details>
				{/if}
			</div>
		{/each}
	</div>
</section>

<style>
	.chat {
		min-height: 80vh;
		padding: 4rem 2rem;
		display: flex;
		flex-direction: column;
		align-items: center;
		max-width: 700px;
		margin: 0 auto;
	}

	.chat__pre {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.75rem;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		color: var(--text-muted);
		margin-bottom: 2rem;
	}

	.chat__chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 1.5rem;
		justify-content: center;
	}

	.chat__chip {
		font-family: 'Inter', sans-serif;
		font-size: 0.85rem;
		padding: 0.5rem 1rem;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 2rem;
		color: var(--text-muted);
		cursor: pointer;
	}

	.chat__chip:hover:not(:disabled) {
		border-color: var(--accent);
		color: var(--accent);
	}

	.chat__form {
		display: flex;
		gap: 0.5rem;
		width: 100%;
		margin-bottom: 2rem;
	}

	.chat__input {
		flex: 1;
		font-family: 'Inter', sans-serif;
		font-size: 0.95rem;
		padding: 0.7rem 1rem;
		background: var(--bg-card);
		color: var(--text);
		border: 1px solid var(--border);
		border-radius: 4px;
	}

	.chat__input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.chat__btn {
		font-family: 'Inter', sans-serif;
		font-size: 0.95rem;
		padding: 0.7rem 1.2rem;
		background: var(--accent);
		color: var(--bg);
		border: 1px solid var(--accent);
		border-radius: 4px;
		cursor: pointer;
		font-weight: 600;
	}

	.chat__transcript {
		width: 100%;
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.chat__entry {
		padding: 1rem;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 6px;
	}

	.chat__q {
		font-weight: 600;
		color: var(--accent);
		margin-bottom: 0.75rem;
		font-size: 0.95rem;
	}

	.chat__a {
		font-size: 0.95rem;
		line-height: 1.6;
	}

	.chat__error {
		color: #c45a5a;
		font-size: 0.9rem;
	}

	.chat__results {
		margin-top: 0.75rem;
		overflow-x: auto;
	}

	.chat__results table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.85rem;
	}

	.chat__results th,
	.chat__results td {
		text-align: left;
		padding: 0.4rem 0.75rem;
		border-bottom: 1px solid var(--border);
	}

	.chat__results th {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.chat__sql-details {
		margin-top: 0.5rem;
	}

	.chat__sql-toggle {
		font-size: 0.8rem;
		color: var(--green);
		cursor: pointer;
	}

	.chat__sql {
		margin-top: 0.5rem;
		padding: 0.75rem;
		background: var(--bg);
		border-radius: 4px;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.8rem;
		color: var(--green);
		white-space: pre-wrap;
		word-break: break-word;
		overflow-x: auto;
	}
</style>
