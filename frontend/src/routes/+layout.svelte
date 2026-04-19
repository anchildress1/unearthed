<script>
	let { children } = $props();
</script>

<svelte:head>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link
		href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=Inter:wght@300;400;600&family=JetBrains+Mono:wght@300;400&display=swap"
		rel="stylesheet"
	/>
</svelte:head>

{@render children()}

<style>
	:global(*) {
		box-sizing: border-box;
		margin: 0;
		padding: 0;
	}

	:global(:root) {
		--bg: #0a0a0a;
		--bg-card: #111111;
		--text: #e8e0d4;
		--text-muted: #7a756e;
		--accent: #c2542d;
		--accent-light: #d4714e;
		--green: #6a8a6a;
		--border: #1e1c1a;
		--font-serif: 'DM Serif Display', serif;
		--font-sans: 'Inter', system-ui, sans-serif;
		--font-mono: 'JetBrains Mono', monospace;
	}

	:global(html) {
		font-size: 16px;
		scroll-behavior: smooth;
	}

	:global(body) {
		font-family: var(--font-sans);
		background: var(--bg);
		color: var(--text);
		line-height: 1.6;
		-webkit-font-smoothing: antialiased;
	}

	:global(a) {
		color: var(--accent);
		text-decoration: none;
	}
</style>
