<script>
	import { reveal } from '$lib/reveal.js';

	let {
		number,
		label,
		children,
		class: className = '',
		reveal: revealOptions = {},
	} = $props();
</script>

<!--
	Editorial two-column section wrapper.

	Left rail: thin vertical column of chrome—a rust section number and a
	short verb/noun that names the section. aria-hidden because it is
	decorative metadata; the real section heading inside the content column
	is what assistive tech reads.

	Right column: where content lives, left-aligned on a wider max-width.
-->
<section class="section-rail {className}" use:reveal={revealOptions}>
	<aside class="rail" aria-hidden="true">
		<span class="rail-num">N° {number}</span>
		<span class="rail-rule"></span>
		<span class="rail-label">{label}</span>
	</aside>
	<div class="rail-content">
		{@render children()}
	</div>
</section>

<style>
	.section-rail {
		display: grid;
		grid-template-columns:
			clamp(64px, 7vw, 104px)
			minmax(0, 1fr);
		column-gap: clamp(1.25rem, 3vw, 2.5rem);
		padding: clamp(3rem, 7vh, 5.5rem) clamp(1.25rem, 4vw, 3rem);
		position: relative;
	}

	/* ---- Left rail ---- */
	.rail {
		grid-column: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		padding-top: clamp(0.5rem, 2vh, 1.5rem);
		gap: 0.9rem;
	}

	.rail-num {
		font-family: var(--mono);
		font-size: 0.7rem;
		font-weight: 400;
		letter-spacing: 0.14em;
		color: var(--rust);
		white-space: nowrap;
	}

	.rail-rule {
		/* Matches the text-column height roughly—long enough to bracket
		   the section copy, short enough not to run into the next section. */
		width: 1px;
		flex: 0 0 clamp(16rem, 52vh, 30rem);
		background: linear-gradient(
			to bottom,
			rgba(255, 255, 255, 0.18),
			rgba(255, 255, 255, 0.02)
		);
	}

	.rail-label {
		font-family: var(--mono);
		font-size: 0.68rem;
		font-weight: 400;
		letter-spacing: 0.22em;
		text-transform: uppercase;
		color: var(--text-dim);
		white-space: nowrap;
	}

	/* ---- Content column (global so sections can extend it) ---- */
	.section-rail > :global(.rail-content) {
		grid-column: 2;
		width: 100%;
		max-width: 900px;
		min-width: 0;
	}

	/* ---- Shared section-header pattern ----
	   Every section gets the same title + subtitle treatment, so "if it's a
	   title, it looks like all other titles." Sections can still cap their
	   header's max-width or override margins, but the typography is canonical
	   here and must not be redefined per section. */
	.section-rail :global(h2),
	.section-rail :global(h3) {
		font-family: var(--serif);
		/* Header scale that the PlantReveal section used before unification —
		   the user's explicit "previously perfect" reference. Every section
		   inherits this now so headers read identically across the page. */
		font-size: clamp(2.5rem, 6vw, 4.5rem);
		font-weight: 400;
		line-height: 1.1;
		letter-spacing: -0.01em;
		color: var(--text);
		margin-bottom: 1.5rem;
	}
	.section-rail :global(h2 em),
	.section-rail :global(h3 em) {
		color: var(--rust);
		font-style: italic;
	}
	.section-rail :global(.sub) {
		font-family: var(--serif);
		font-size: 0.95rem;
		font-weight: 300;
		line-height: 1.7;
		color: var(--text-dim);
		max-width: 640px;
	}
	.section-rail :global(.sub strong) {
		color: var(--text);
		font-weight: 400;
	}
	.section-rail :global(.sub .rust) {
		color: var(--rust);
		font-style: italic;
	}
	.section-rail :global(.sub .ash) {
		color: #a89e92;
		font-style: italic;
	}
	.section-rail :global(.sub em) {
		color: var(--rust);
		font-style: italic;
	}

	/* ---- Three-line anchor-text pattern ----
	   Every "value + primary label + secondary label" trio reuses the same
	   typography: big number on its own line, serif explanation underneath,
	   mono uppercase tag at the bottom. Used by PlantReveal cards, the
	   acres-and-football-fields mountain block, the emissions panel, and
	   the H3 density tallies. Do not re-declare these per section — if a
	   section's trio needs a larger primary (Ticker's closing counter),
	   define a distinct class rather than overriding these in section
	   scope, so the canonical pattern stays consistent by default. */
	.section-rail :global(.anchor-primary) {
		font-family: var(--serif);
		font-size: 0.82rem;
		font-weight: 400;
		color: var(--text-dim);
		line-height: 1.25;
		margin-top: 0.2rem;
	}
	.section-rail :global(.anchor-secondary) {
		font-family: var(--mono);
		font-size: 0.5rem;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		color: var(--text-ghost);
		line-height: 1.3;
	}

	/* Cortex-context explanation block. The rust border-left is the
	   sitewide signal for "this text was written by Cortex." Used by
	   H3Density's density summary and the CortexChat hint. */
	.section-rail :global(.cortex-note) {
		font-family: var(--serif);
		font-size: 0.95rem;
		font-weight: 300;
		line-height: 1.7;
		color: var(--text);
		margin-top: 1.3rem;
		padding: 0.8rem 1rem;
		background: oklch(58% 0.14 36 / 0.06);
		border-left: 2px solid var(--rust);
		border-radius: 3px;
	}
	.section-rail :global(.cortex-note-tag) {
		display: block;
		font-family: var(--mono);
		font-size: 0.55rem;
		text-transform: uppercase;
		letter-spacing: 0.2em;
		color: var(--rust);
		margin-bottom: 0.4rem;
	}

	@media (max-width: 720px) {
		.section-rail {
			grid-template-columns: minmax(0, 1fr);
			column-gap: 0;
			padding: clamp(2.5rem, 6vh, 4rem) 1.25rem;
		}
		.rail {
			display: none;
		}
		.section-rail > :global(.rail-content) {
			grid-column: 1;
		}
	}
</style>
