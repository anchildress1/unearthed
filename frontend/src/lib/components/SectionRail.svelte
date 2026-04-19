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
	Editorial section wrapper. The chrome (N° / hairline / rotated label) is a
	narrow vertical rail pinned in the left gutter, matching the Hero section's
	signature column. Content flows in a flex column to the right of the rail
	so every section below the hero reads as a continuation of the same
	magazine-spread frame — not as disconnected full-bleed blocks.

	aria-hidden on the chrome because it's decorative; the real section heading
	inside the content is what assistive tech reads.
-->
<section class="section-rail {className}" use:reveal={revealOptions}>
	<div class="section-layout">
		<header class="rail-chrome" aria-hidden="true">
			<span class="rail-num">N° {number}</span>
			<span class="rail-rule"></span>
			<span class="rail-label">{label}</span>
		</header>
		<div class="rail-content">
			{@render children()}
		</div>
	</div>
</section>

<style>
	.section-rail {
		display: block;
		padding: clamp(3rem, 7vh, 5.5rem) clamp(1.5rem, 5vw, 4rem);
		position: relative;
	}

	/* ---- Editorial two-column layout ----
	   Mirrors Hero's `.hero-layout`: a narrow left-gutter rail + a content
	   column that fills the rest of the frame. `align-items: stretch` so
	   the rail runs the full height of the content block and the hairline
	   reads as the section's editorial spine. */
	.section-layout {
		display: flex;
		align-items: stretch;
		gap: clamp(1.25rem, 3vw, 2.25rem);
		width: 100%;
	}

	/* ---- Vertical chrome rail ----
	   N° caps the top, rotated label anchors the bottom, hairline rule
	   flexes to fill whatever distance sits between them. Same construction
	   Hero uses so the mark reads as a single, continuous page signature
	   from section 01 through the end of the story. */
	.rail-chrome {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.8rem;
		flex: 0 0 auto;
		padding: 0.35rem 0;
	}

	.rail-num {
		display: block;
		font-family: var(--mono);
		font-size: 0.7rem;
		font-weight: 400;
		letter-spacing: 0.14em;
		color: var(--rust);
		white-space: nowrap;
	}

	/* 1px-wide vertical hairline. `display: block` is required because the
	   element is an empty <span>; without it the width/height won't paint
	   reliably. The gradient fades both ends so the rule feels etched
	   rather than stamped. */
	.rail-rule {
		display: block;
		width: 1px;
		flex: 1 1 auto;
		min-height: 3rem;
		align-self: center;
		background: linear-gradient(
			to bottom,
			rgba(255, 255, 255, 0.04),
			rgba(255, 255, 255, 0.22) 15%,
			rgba(255, 255, 255, 0.22) 85%,
			rgba(255, 255, 255, 0.04)
		);
	}

	.rail-label {
		display: block;
		font-family: var(--mono);
		font-size: 0.68rem;
		font-weight: 400;
		letter-spacing: 0.22em;
		text-transform: uppercase;
		color: var(--text-dim);
		white-space: nowrap;
		/* Real sideways text (not a transform rotation) so the label stays
		   accessible to screen readers even though the parent is aria-hidden.
		   `rotate(180deg)` flips the glyph-order so the label reads bottom-
		   to-top, aligning with the rail's visual spine. */
		writing-mode: vertical-rl;
		transform: rotate(180deg);
	}

	/* ---- Content column ----
	   Flex-1 so the column owns every pixel the rail doesn't. Each section
	   caps its own reading-measure inside (PlantReveal's prose at 600px,
	   H3Density's header at 720px, etc.); this wrapper just guarantees the
	   rail and the content live in the same editorial frame. */
	.section-rail > .section-layout > :global(.rail-content) {
		flex: 1 1 0;
		min-width: 0;
		width: 100%;
	}

	/* ---- Shared section-header pattern ----
	   Every section gets the same title + subtitle treatment, so "if it's a
	   title, it looks like all other titles." Sections can still cap their
	   header's max-width or override margins, but the typography is canonical
	   here and must not be redefined per section. */
	.section-rail :global(h2),
	.section-rail :global(h3) {
		font-family: var(--serif);
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
	/* Degraded = Cortex fallback template fired. Dim the rust accent and
	   swap the tag copy upstream so template prose doesn't ride under a
	   "Cortex, on this map" byline. The ghost ash tone marks the note as
	   "static copy" without hiding it entirely — the facts still matter. */
	.section-rail :global(.cortex-note.degraded) {
		background: rgba(255, 255, 255, 0.025);
		border-left-color: var(--text-ghost);
		color: var(--text-dim);
	}
	.section-rail :global(.cortex-note.degraded .cortex-note-tag) {
		color: var(--text-ghost);
	}

	@media (max-width: 720px) {
		.section-rail {
			padding: clamp(2.5rem, 6vh, 4rem) 1.25rem;
		}
		/* Collapse the two-column editorial layout into a single column on
		   narrow screens — the chrome stacks above the content with the
		   label reading left-to-right again. Same collapse pattern as Hero. */
		.section-layout {
			flex-direction: column;
			gap: 1rem;
		}
		.rail-chrome {
			flex-direction: row;
			align-items: center;
			gap: 0.8rem;
			padding: 0;
		}
		.rail-rule {
			width: 2rem;
			height: 1px;
			min-height: 0;
			flex: 0 0 2rem;
			background: linear-gradient(
				to right,
				rgba(255, 255, 255, 0.22),
				rgba(255, 255, 255, 0.04)
			);
		}
		.rail-label {
			writing-mode: horizontal-tb;
			transform: none;
		}
	}
</style>
