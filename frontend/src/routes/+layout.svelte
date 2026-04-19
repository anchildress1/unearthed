<script>
	let { children } = $props();
</script>

<svelte:head>
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
		--bg: #080808;
		--text: #e8e0d4;
		--text-dim: #9a9490;
		--text-ghost: #807b75;
		--accent: #c2542d;
		--accent-glow: rgba(194, 84, 45, 0.15);
		--green: #5a7a5a;
		--border-glass: rgba(255, 255, 255, 0.07);
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
		color: var(--accent);
		text-decoration: none;
	}

	:global(strong), :global(b) {
		font-weight: 600;
		color: var(--text);
	}

	/* Override the browser's default blue text-selection highlight, which
	   reads as accessibility-failing chrome against the site's rust/ash
	   palette. Use the site's accent at low opacity with the text kept at
	   the base fore color so selected text stays legible. */
	:global(::selection) {
		background: rgba(194, 84, 45, 0.38);
		color: var(--text);
	}
	:global(::-moz-selection) {
		background: rgba(194, 84, 45, 0.38);
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
		color: rgba(128, 123, 117, 0.6);
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
