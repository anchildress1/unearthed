<script>
	import { fetchAsk } from '$lib/api.js';
	import SectionRail from '$lib/components/SectionRail.svelte';

	const props = $props();
	let question = $state('');
	// Single-entry view—asking a new question replaces the prior one so the
	// page stays focused on the latest answer instead of growing a scrolling
	// transcript the user has to hunt through.
	let entry = $state(null);
	let asking = $state(false);
	// SQL + interpretation are *proof* (for judges, for skeptics), but most
	// users just want the answer. Collapsed by default; expanded per-entry
	// via this flag when the user clicks "show how Cortex got there".
	let showProof = $state(false);

	const chips = $derived([
		`How much has ${props.mineName} produced since 2020?`,
		`Which mines supplied ${props.plantName} in 2024? Rank by tonnage.`,
		`Is ${props.mineName} still active?`,
		`How many fatalities at ${props.mineName}?`,
		`Who is the largest coal supplier in Wyoming?`,
	]);

	async function ask(q) {
		if (asking || !q.trim()) return;
		asking = true;
		showProof = false;
		console.log('[unearthed] cortex query:', q);
		entry = {
			question: q,
			answer: null,
			interpretation: null,
			error: null,
			sql: null,
			results: null,
			suggestions: [],
		};
		question = '';
		try {
			const result = await fetchAsk(q, props.subregionId);
			entry = {
				...entry,
				answer: result.answer || '',
				interpretation: result.interpretation || '',
				sql: result.sql,
				error: result.error,
				results: result.results,
				suggestions: !result.sql ? result.suggestions || [] : [],
			};
			console.log('[unearthed] cortex response:', entry.answer?.slice(0, 100));
		} catch (e) {
			console.error('[unearthed] cortex error:', e);
			entry = { ...entry, error: 'Could not reach the data assistant.' };
		} finally {
			asking = false;
		}
	}

	function handleSubmit(e) {
		e.preventDefault();
		ask(question);
	}

	// Cortex result rows are arbitrary JSON — a nested struct or variant cell
	// would render as "[object Object]" via default coercion, which looks
	// broken next to formatted numbers. JSON-stringify objects so the raw
	// shape is visible instead of the coercion artifact.
	function formatCell(val) {
		if (val == null) return '';
		if (typeof val === 'number') return val.toLocaleString();
		if (typeof val === 'object') return JSON.stringify(val);
		return val;
	}
</script>

<SectionRail number="05" label="Ask the records" class="cortex-section">
	<div class="header">
		<span class="badge">
			<span class="pulse" aria-hidden="true"></span>
			<span>snowflake cortex analyst</span>
			{#if asking}
				<span class="status active">querying</span>
			{/if}
		</span>
	</div>

	<h2>Interrogate the <em>records</em>.</h2>

	<!--
		`.cortex-shell` caps the interactive UI at a sensible reading width
		even though the section's headline above is free to span the full
		content column. The form, pipeline, chips, and results all need a
		line-length that reads like prose, not a dashboard. The headline
		above opts out of this cap by sitting outside the wrapper.
	-->
	<div class="cortex-shell">
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

	<div class="chips" role="group" aria-label="Suggested questions">
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

	{#if entry}
		<div class="entry glass">
			<p class="q"><span class="q-mark">&gt;</span> {entry.question}</p>

			{#if asking}
				<div class="typing" aria-label="Querying Snowflake…">
					<span class="dot"></span>
					<span class="dot"></span>
					<span class="dot"></span>
				</div>
			{/if}

			{#if entry.error}
				<p class="error">{entry.error}</p>
			{/if}

			{#if entry.answer}
				<p class="answer">{entry.answer}</p>
			{/if}

			{#if entry.results && entry.results.length === 0 && !entry.error}
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
										<td>{formatCell(val)}</td>
									{/each}
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}

			{#if !entry.sql && !entry.error && entry.answer}
				<p class="hint">
					Cortex answered from its interpretation layer without running a query.
					Try rephrasing with a specific mine, plant, operator, or state name—or pick one below.
				</p>
			{/if}

			{#if entry.suggestions && entry.suggestions.length > 0}
				<div class="follow-ups">
					{#each entry.suggestions as suggestion}
						<button class="chip" onclick={() => ask(suggestion)} disabled={asking}>
							{suggestion}
						</button>
					{/each}
				</div>
			{/if}

			{#if entry.sql || entry.interpretation}
				<!--
					Proof drawer. Everyday readers want the answer; judges and
					skeptics want to see Cortex's work. Hidden by default,
					expanded on click—the tag below doubles as the affordance.
				-->
				<button
					type="button"
					class="proof-toggle"
					aria-expanded={showProof}
					aria-controls="cortex-proof"
					onclick={() => (showProof = !showProof)}
				>
					<span class="caret" aria-hidden="true">{showProof ? '▾' : '▸'}</span>
					{showProof ? 'hide' : 'show'} how Cortex got there
				</button>
				{#if showProof}
					<div class="proof" id="cortex-proof">
						{#if entry.sql}
							<div class="proof-stage">
								<span class="stage-num">02</span>
								<span class="stage-label">generated SQL · Cortex Analyst</span>
							</div>
							<pre class="sql-pre">{entry.sql}</pre>
						{/if}
						{#if entry.interpretation}
							<div class="proof-stage">
								<span class="stage-num">03</span>
								<span class="stage-label">Cortex interpretation</span>
							</div>
							<p class="interp">{entry.interpretation}</p>
						{/if}
					</div>
				{/if}
			{/if}
		</div>
	{/if}
	</div>
</SectionRail>

<style>
	.header {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-bottom: 1rem;
	}

	/* Reading measure for the interactive UI. SectionRail no longer caps
	   the content column (so the h2 above can breathe edge-to-edge), but
	   the form + pipeline + chips + results table all want line-lengths
	   closer to prose than to a dashboard. 1040px matches the canonical
	   map-frame width elsewhere on the page. */
	.cortex-shell {
		max-width: min(1040px, 100%);
	}

	.badge {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		font-family: var(--mono);
		font-size: 0.6rem;
		text-transform: uppercase;
		letter-spacing: 0.2em;
		color: var(--rust);
		border: 1px solid oklch(64% 0.145 36 / 0.3);
		padding: 0.3rem 0.65rem 0.3rem 0.55rem;
		border-radius: 3px;
	}

	/* Soft breathing dot. Rust dim → bright tier → dim, matching the two-
	   tier palette. Reduced-motion fallback keeps the dot visible but still
	   — the animation is purely decorative and nothing depends on it. */
	.pulse {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--rust);
		box-shadow: 0 0 0 0 var(--rust-glow);
		animation: cortex-pulse 2.2s ease-in-out infinite;
	}
	@keyframes cortex-pulse {
		0%, 100% {
			background: var(--rust);
			box-shadow: 0 0 0 0 oklch(64% 0.145 36 / 0);
		}
		50% {
			background: var(--rust-bright);
			box-shadow: 0 0 0 4px oklch(64% 0.145 36 / 0.18);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.pulse { animation: none; }
	}

	.status {
		color: var(--text-ghost);
		font-size: 0.5rem;
		letter-spacing: 0.18em;
		padding-left: 0.4rem;
		border-left: 1px solid oklch(64% 0.145 36 / 0.25);
	}
	.status.active { color: var(--rust-bright); }

	/* The form chrome sits too close to the sub paragraph without an extra
	   breath of space before it—the rest of the sections end their header
	   on the h2 or a summary block, so this nudge is specific to CortexChat. */
	.sub {
		margin-bottom: 1.4rem;
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
		color: var(--rust);
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
	.chip:hover:not(:disabled) { border-color: var(--rust); color: var(--rust); }
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
	input:focus { border-color: var(--rust); }
	input::placeholder { color: var(--text-ghost); font-style: italic; }

	button[type="submit"] {
		font-family: var(--mono);
		font-size: 0.7rem;
		padding: 0.7rem 1rem;
		background: var(--rust);
		color: #fff;
		border: none;
		border-radius: 6px;
		cursor: pointer;
		letter-spacing: 0.08em;
	}
	button[type="submit"]:disabled { opacity: 0.3; cursor: not-allowed; }

	.entry { padding: 1.3rem 1.5rem; }

	.q {
		font-family: var(--serif);
		font-weight: 400;
		font-style: italic;
		font-size: 1.05rem;
		color: var(--text);
		line-height: 1.5;
		margin-bottom: 0.6rem;
	}
	.q-mark {
		font-family: var(--mono);
		font-style: normal;
		font-size: 0.65rem;
		color: var(--rust);
		letter-spacing: 0.1em;
		margin-right: 0.4rem;
	}

	/* Pill-style toggle so the caret + border read unmistakably as "this is
	   a button that toggles". The caret flips between ▸ (collapsed) and ▾
	   (expanded) to reinforce the two-way affordance. */
	.proof-toggle {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		margin-top: 0.9rem;
		padding: 0.4rem 0.8rem;
		background: rgba(255, 255, 255, 0.02);
		border: 1px solid var(--border-glass);
		border-radius: 2rem;
		font-family: var(--mono);
		font-size: 0.6rem;
		text-transform: uppercase;
		letter-spacing: 0.15em;
		color: var(--text-ghost);
		cursor: pointer;
		transition: color 0.15s, border-color 0.15s, background 0.15s;
	}
	.proof-toggle:hover {
		color: var(--rust);
		border-color: oklch(64% 0.145 36 / 0.45);
		background: oklch(64% 0.145 36 / 0.06);
	}
	.proof-toggle[aria-expanded="true"] {
		color: var(--rust);
		border-color: oklch(64% 0.145 36 / 0.35);
	}
	.proof-toggle .caret {
		font-size: 0.7rem;
		line-height: 1;
		transform: translateY(-0.5px);
	}

	.proof {
		margin-top: 0.6rem;
		padding-top: 0.8rem;
		border-top: 1px solid rgba(255, 255, 255, 0.05);
	}
	.proof-stage {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		margin-top: 0.9rem;
		margin-bottom: 0.4rem;
	}
	.proof-stage:first-child { margin-top: 0; }
	.stage-num {
		font-family: var(--mono);
		font-size: 0.6rem;
		color: var(--rust);
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
	.interp {
		font-family: var(--serif);
		font-size: 0.9rem;
		font-weight: 300;
		line-height: 1.7;
		color: var(--text-dim);
		font-style: italic;
	}

	.typing {
		display: flex;
		gap: 0.35rem;
		padding: 0.6rem 0;
	}
	.dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--text-ghost);
		animation: pulse 1.4s ease-in-out infinite;
	}
	.dot:nth-child(2) { animation-delay: 0.2s; }
	.dot:nth-child(3) { animation-delay: 0.4s; }
	@keyframes pulse {
		0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); }
		40% { opacity: 1; transform: scale(1); }
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
		color: var(--rust);
		font-size: 0.85rem;
		font-style: italic;
	}

	.no-results {
		font-family: var(--mono);
		font-size: 0.7rem;
		color: var(--text-ghost);
		font-style: italic;
	}

	.hint {
		font-family: var(--serif);
		font-size: 0.85rem;
		font-style: italic;
		color: var(--text-dim);
		line-height: 1.55;
		margin: 0.4rem 0 0.6rem;
		padding-left: 0.75rem;
		border-left: 2px solid oklch(64% 0.145 36 / 0.45);
	}

	.follow-ups {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin: 0.4rem 0 0.2rem;
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
		border-left: 2px solid var(--rust);
		font-family: var(--mono);
		font-size: 0.72rem;
		color: var(--rust);
		white-space: pre-wrap;
		word-break: break-word;
		line-height: 1.55;
		overflow-x: auto;
	}
</style>
