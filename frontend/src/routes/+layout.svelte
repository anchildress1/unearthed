<script>
	let { children } = $props();
</script>

<svelte:head>
	<!--
		Inline SVG favicon (primary) + `static/favicon.ico` (legacy fallback
		for older browsers and crawlers that still request `/favicon.ico`
		by convention). The SVG is a single rust disc over the page
		background tone; the .ico mirrors the same mark so the site never
		surfaces a default-browser favicon. Both together close the
		`errors-in-console` Lighthouse check that a missing /favicon.ico
		would trip and tank best-practices below the 0.98 gate.
	-->
	<link
		rel="icon"
		type="image/svg+xml"
		href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%23070605'/%3E%3Ccircle cx='16' cy='16' r='9' fill='%23a85639'/%3E%3C/svg%3E"
	/>
	<link rel="icon" href="/favicon.ico" sizes="any" />
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link
		href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,600;1,6..72,300;1,6..72,400;1,6..72,600&family=JetBrains+Mono:wght@300;400&display=swap"
		rel="stylesheet"
	/>
</svelte:head>

<div class="bg-fixed" aria-hidden="true"></div>
<div class="bg-grain" aria-hidden="true"></div>
<!--
	Photo attribution lives with the fixed background, not inside any one
	section. `position: fixed` pins it to the viewport so it stays visible
	for as long as the photo is — which is the entire page, since .bg-fixed
	is the site-wide background. Moving this out of Hero fixes the "credit
	scrolls away while the photo it credits is still on screen" bug.

	Wrapped in `<aside aria-label>` so the credit sits inside an explicit
	complementary landmark — axe-core's `region` rule flags top-level page
	content that isn't contained by a landmark, and `<main>` / `<footer>`
	both fit the content they own but not this viewport-fixed link. The
	wrapper is in flow but its only child is `position: fixed`, so it
	contributes zero layout.
-->
<aside class="photo-credit-landmark" aria-label="Background photo credit">
	<a
		class="photo-credit"
		href="https://www.flickr.com/photos/nationalmemorialforthemountains/255887679/"
		target="_blank"
		rel="noopener"
	>
		Photo: Kent Kessinger · iLoveMountains.org<br/>Flight courtesy SouthWings
	</a>
</aside>
{@render children()}

<!--
	Site-wide credits. Single footer for the whole page — section-internal
	credits (Ticker previously carried its own) have been consolidated here
	so links appear once, at the bottom, and the page body stays focused
	on the story instead of repeated attribution rows.
-->
<footer class="site-footer">
	<p>© 2026 Ashley Childress</p>
	<p class="data-credit">
		Data:
		<a href="https://www.msha.gov/" target="_blank" rel="noopener">MSHA</a> ·
		<a href="https://www.eia.gov/" target="_blank" rel="noopener">EIA</a> ·
		<a href="https://www.epa.gov/egrid" target="_blank" rel="noopener">EPA eGRID</a>
		· AI:
		<a href="https://www.snowflake.com/en/data-cloud/cortex/" target="_blank" rel="noopener">Snowflake Cortex</a>
	</p>
	<!--
		Two donate affordances side-by-side. Both `href`s are placeholders —
		swap once accounts are claimed. Buy Me a Coffee covers tip-style
		one-offs; GitHub Sponsors covers recurring dev-support. Same chrome
		(hairline rust pill, mono caps) so they read as one row of options
		instead of competing CTAs.
	-->
	<p class="donate">
		<a
			href="https://buymeacoffee.com/REPLACE-ME"
			target="_blank"
			rel="noopener"
			aria-label="Buy me a coffee"
		>
			Buy me a coffee
		</a>
		<a
			href="https://github.com/sponsors/REPLACE-ME"
			target="_blank"
			rel="noopener"
			aria-label="Sponsor on GitHub"
		>
			Sponsor on GitHub
		</a>
	</p>
</footer>

<style>
	:global(*) {
		box-sizing: border-box;
		margin: 0;
		padding: 0;
	}

	:global(:root) {
		--bg: #070605;
		--text: #e8dfcc;
		--text-dim: #a89e8c;
		/* --text-ghost is the dimmest legible tone — footer copy, anchor-
		   secondary captions, map legends, every "on the margins" label.
		   Luminance-tuned so 8-10px body copy still clears WCAG AA (≥4.5:1)
		   against the near-black --bg; darker than that looked editorial
		   but failed accessibility audits outright. */
		--text-ghost: #a09488;
		/* Two-tier rust palette. --rust is the iron-oxide primary: it carries
		   nearly every accent surface (text ems, rules, card values, the one
		   map route). --rust-bright is held back for charged moments where
		   the page needs to shout (text selection, forthcoming live pulses).
		   The OKLCH values are perceptually chosen — same hue, two
		   luminances — so the bright tier reads as the same color, louder.
		   Lightness sits at 64% so small-text uses (span.rail-num, .primary,
		   .geo-btn, .e-value, emissions-source strong) clear WCAG AA ≥4.5:1
		   against --bg and the dark-glass overlays; the prior 58% read as
		   editorially right but failed the deployed Lighthouse audit. */
		--rust: oklch(64% 0.145 36);
		--rust-bright: oklch(76% 0.18 38);
		--rust-glow: oklch(64% 0.145 36 / 0.15);
		--green: #5a7a5a;
		--border-glass: rgba(255, 255, 255, 0.07);
		/* Hairline divider used for the ledger-look stat grids: sits between
		   cards as a 1px bleed of the wrapper background. Just barely brighter
		   than --glass-bg so the rule reads as intentional structure instead of
		   a compositor seam. */
		--rule: rgba(255, 255, 255, 0.06);
		--glass-bg: rgba(255, 255, 255, 0.03);
		--glass-blur: blur(14px);
		--serif: 'Newsreader', Georgia, serif;
		--mono: 'JetBrains Mono', ui-monospace, monospace;
		--section-pad: clamp(2rem, 5vw, 6rem);
	}

	:global(html) {
		font-size: 16px;
		scroll-behavior: smooth;
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
	}

	:global(body) {
		font-family: var(--serif);
		font-weight: 300;
		background: var(--bg);
		color: var(--text);
		line-height: 1.7;
		overflow-x: hidden;
	}

	:global(a) {
		color: var(--rust);
		text-decoration: none;
	}

	:global(strong), :global(b) {
		font-weight: 600;
		color: var(--text);
	}

	/* Sitewide accent-color utility classes. Inline `<span class="rust">`
	   and `<span class="ash">` in prose stay symmetric — both carry a
	   color, neither depends on a section-scoped style accidentally
	   leaking globally. Scoped so it only takes effect when written
	   explicitly on a span/em; section headings still use the canonical
	   `h2 em` / `h3 em` rust treatment in SectionRail. */
	:global(.rust) {
		color: var(--rust);
	}
	:global(.ash) {
		color: #a89e92;
	}

	/* Override the browser's default blue text-selection highlight, which
	   reads as accessibility-failing chrome against the site's rust/ash
	   palette. Selection is the one moment the page earns the bright tier:
	   it's a direct response to a user gesture, so the louder rust reads as
	   interactive feedback without needing extra UI. Text stays at the base
	   fore color so selected copy is still legible. */
	:global(::selection) {
		background: oklch(70% 0.17 38 / 0.38);
		color: var(--text);
	}
	:global(::-moz-selection) {
		background: oklch(70% 0.17 38 / 0.38);
		color: var(--text);
	}

	/* ---- Fixed mountain scar ----
	   position:fixed + inset:0 is not enough on its own: on iOS Safari the
	   address bar collapsing during scroll changes the viewport height, and
	   on some desktop browsers the sibling-scroll compositor repaints the
	   layer, both of which show up as a tiny visible shift. Promoting the
	   element to its own GPU layer via translate3d + will-change pins it so
	   the painter never touches it on scroll. Height is locked in pixels at
	   page load (the svh unit holds the initial viewport height) so the
	   browser UI collapse can't drag the gradient with it. */
	.bg-fixed {
		position: fixed;
		top: 0;
		left: 0;
		width: 100vw;
		height: 100svh;
		z-index: -2;
		background: url('/img/westva-strip-mine.webp') center 35% / cover no-repeat;
		opacity: 0.38;
		will-change: transform;
		transform: translate3d(0, 0, 0);
		backface-visibility: hidden;
	}
	.bg-fixed::after {
		content: '';
		position: absolute;
		inset: 0;
		background:
			radial-gradient(ellipse 70% 55% at 40% 40%, transparent 0%, var(--bg) 100%),
			linear-gradient(to top, var(--bg) 0%, transparent 40%),
			linear-gradient(to bottom, var(--bg) 0%, transparent 30%),
			linear-gradient(to left, var(--bg) 0%, transparent 35%),
			linear-gradient(to right, var(--bg) 0%, transparent 35%);
	}

	/* Film grain texture—same GPU-layer trick as the scar image. */
	.bg-grain {
		position: fixed;
		top: 0;
		left: 0;
		width: 100vw;
		height: 100svh;
		z-index: -1;
		opacity: 0.035;
		pointer-events: none;
		background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
		background-repeat: repeat;
		background-size: 256px;
		will-change: transform;
		transform: translate3d(0, 0, 0);
		backface-visibility: hidden;
	}

	/* Site-wide photo attribution. Fixed to the viewport so it sticks while
	   the background does. Larger than the previous hero-local credit
	   (0.52rem was too small to read) and in the ghost tone so it doesn't
	   compete with primary content. */
	.photo-credit {
		position: fixed;
		bottom: clamp(1rem, 2.5vh, 1.5rem);
		right: clamp(1.25rem, 3vw, 2.5rem);
		z-index: 5;
		font-family: var(--mono);
		font-size: 0.7rem;
		line-height: 1.5;
		letter-spacing: 0.04em;
		text-align: right;
		text-decoration: none;
		color: var(--text-ghost);
		opacity: 0.7;
		transition: opacity 0.25s;
	}
	.photo-credit:hover,
	.photo-credit:focus-visible {
		opacity: 1;
		color: var(--text-dim);
	}

	@media (max-width: 720px) {
		.photo-credit {
			font-size: 0.62rem;
			bottom: 0.75rem;
			right: 0.9rem;
			line-height: 1.4;
		}
	}

	@media (max-width: 768px) {
		.bg-fixed {
			background-image: url('/img/westva-strip-mine-768.webp');
			opacity: 0.25;
		}
	}

	/* ---- Site footer ---- */
	.site-footer {
		padding: 2.5rem var(--section-pad) 2rem;
		margin-top: 2rem;
		border-top: 1px solid rgba(255, 255, 255, 0.05);
		text-align: center;
		font-family: var(--mono);
		font-size: 0.62rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--text-ghost);
	}
	.site-footer p { margin: 0; }
	.site-footer .data-credit {
		margin-top: 0.5rem;
		font-size: 0.55rem;
		letter-spacing: 0.1em;
		/* Solid tone rather than an alpha-composite — alpha against
		   near-black crushed to a 2.4:1 ratio and failed contrast
		   audits. 4.9:1 as a solid color still reads quieter than the
		   line above it because the font is smaller and the tracking
		   is wider. */
		color: #857c70;
	}
	/* Credit links are the same dim tone as the surrounding text with a
	   subtle underline to mark them as affordances. Hover lifts to the
	   rust accent used everywhere else on the page. */
	.site-footer .data-credit a {
		color: var(--text-dim);
		text-decoration: underline;
		text-decoration-color: rgba(255, 255, 255, 0.12);
		text-underline-offset: 2px;
		transition: color 0.15s, text-decoration-color 0.15s;
	}
	.site-footer .data-credit a:hover,
	.site-footer .data-credit a:focus-visible {
		color: var(--rust);
		text-decoration-color: var(--rust);
	}

	/* Donate row sits below the data credit. Hairline rust border + mono
	   caps so each affordance reads as a quiet option, not a CTA shouting
	   at the reader. Hover fills to the bright tier — same gesture-
	   feedback convention as ::selection elsewhere on the site. The row
	   uses inline-flex with a small gap so the two buttons sit on one line
	   on desktop and wrap cleanly on mobile. */
	.site-footer .donate {
		margin-top: 1.25rem;
		display: flex;
		justify-content: center;
		gap: 0.6rem;
		flex-wrap: wrap;
	}
	.site-footer .donate a {
		display: inline-block;
		padding: 0.5rem 1.1rem;
		font-family: var(--mono);
		font-size: 0.6rem;
		letter-spacing: 0.18em;
		text-transform: uppercase;
		color: var(--rust);
		border: 1px solid var(--rust);
		border-radius: 999px;
		text-decoration: none;
		transition: color 0.2s, background 0.2s, border-color 0.2s;
	}
	.site-footer .donate a:hover,
	.site-footer .donate a:focus-visible {
		color: var(--bg);
		background: var(--rust-bright);
		border-color: var(--rust-bright);
	}

	/* ---- Glass utility ---- */
	:global(.glass) {
		background: var(--glass-bg);
		-webkit-backdrop-filter: var(--glass-blur);
		backdrop-filter: var(--glass-blur);
		border: 1px solid var(--border-glass);
		box-shadow:
			0 8px 32px rgba(0, 0, 0, 0.35),
			inset 0 1px 0 rgba(255, 255, 255, 0.04);
		border-radius: 12px;
	}
</style>
