<script>
	let { children } = $props();
</script>

<svelte:head>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link
		href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400;1,700&family=Inter:wght@300;400;600&family=JetBrains+Mono:wght@300;400&display=swap"
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

	:global(html) {
		font-size: 16px;
		scroll-behavior: smooth;
	}

	:global(body) {
		font-family: 'Inter', system-ui, sans-serif;
		background: #0a0a0a;
		color: #d4d0c8;
		line-height: 1.6;
		-webkit-font-smoothing: antialiased;
	}

	:global(a) {
		color: #c4956a;
		text-decoration: none;
	}
</style>
