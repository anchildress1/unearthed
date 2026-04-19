// Scroll-reveal Svelte action. Applies fade + translate when the node enters view.
// Once revealed, stays revealed (no re-hiding on scroll back).
//
// Usage: <section use:reveal> or <section use:reveal={{ delay: 120 }}>

export function reveal(node, options = {}) {
	const delay = options.delay ?? 0;
	const threshold = options.threshold ?? 0.12;
	const distance = options.distance ?? 28;

	// Respect prefers-reduced-motion — no animation, just show.
	const prefersReduced =
		typeof window !== 'undefined' &&
		window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

	if (prefersReduced) return { destroy() {} };

	node.style.opacity = '0';
	node.style.transform = `translateY(${distance}px)`;
	node.style.transition = `opacity 1.1s ${delay}ms cubic-bezier(0.2, 0.65, 0.2, 1), transform 1.1s ${delay}ms cubic-bezier(0.2, 0.65, 0.2, 1)`;

	const observer = new IntersectionObserver(
		(entries) => {
			for (const entry of entries) {
				if (entry.isIntersecting) {
					node.style.opacity = '1';
					node.style.transform = 'translateY(0)';
					observer.unobserve(node);
				}
			}
		},
		{ threshold, rootMargin: '0px 0px -8% 0px' }
	);
	observer.observe(node);

	return {
		destroy() {
			observer.disconnect();
		},
	};
}
