<script>
	import SectionRail from './SectionRail.svelte';

	let { number, label, body, className = '' } = $props();
</script>

<SectionRail {number} {label} class={className}>
	<p>{body}</p>
</SectionRail>
