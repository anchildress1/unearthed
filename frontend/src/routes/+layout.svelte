<script>
	let { children } = $props();
</script>

<svelte:head>
	<!--
		Inline SVG favicon: a single rust disc over the page background tone.
		Avoids a /favicon.ico 404 — which Lighthouse flags as a console error
		and tanks best-practices below the 0.98 gate — without shipping a
		binary asset.
	-->
	<link
		rel="icon"
		type="image/svg+xml"
		href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%23070605'/%3E%3Ccircle cx='16' cy='16' r='9' fill='%23a85639'/%3E%3C/svg%3E"
	/>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link
		href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,600;1,6..72,300;1,6..72,400;1,6..72,600&family=JetBrains+Mono:wght@300;400&display=swap"
		rel="stylesheet"
	/>
</svelte:head>

<div class="bg-fixed" aria-hidden="true"></div>
<div class="bg-grain" aria-hidden="true"></div>
{@render children()}

<footer class="site-footer">
	<p>© 2026 Ashley Childress</p>
	<p class="data-credit">
		Federal public-domain data: MSHA · EIA · EPA · eGRID ·
		via Snowflake Cortex + Marketplace
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
		/* Two-tier rust palette. --rust is the dim, iron-oxide primary: it
		   carries nearly every accent surface (text ems, rules, card values,
		   the one map route). --rust-bright is held back for charged moments
		   where the page needs to shout (text selection, forthcoming live
		   pulses). The OKLCH values are perceptually chosen — same hue, two
		   luminances — so the bright tier reads as the same color, louder. */
		--rust: oklch(58% 0.14 36);
		--rust-bright: oklch(70% 0.17 38);
		--rust-glow: oklch(58% 0.14 36 / 0.15);
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
